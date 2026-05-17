"""
src/graph/nodes.py — LangGraph nodes for the IaC Generator.

NODE RESPONSIBILITIES
─────────────────────
  clarify  → extract structured requirements from the raw user prompt
  plan     → produce an ordered resource dependency list
  generate → write HCL files for every resource in the plan
  validate → run terraform validate; populate validation_errors on failure
  output   → write files to disk, set final_status
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import IacGenState
from src.tools.file_tool import write_terraform_files
from src.tools.terraform_tool import validate_generated_files

log = logging.getLogger(__name__)

# ── LLM setup ─────────────────────────────────────────────────────────────────

def _llm() -> ChatAnthropic:
    model = os.environ.get("IAC_MODEL", "claude-sonnet-4-6")
    return ChatAnthropic(model=model, max_tokens=8192)


# ── Helper: load reference templates ──────────────────────────────────────────

def _load_templates() -> str:
    """
    Load all HCL reference templates from the templates/ directory.
    These give the LLM correct argument names and structure to avoid hallucination.
    """
    templates_dir = Path(__file__).parent.parent.parent / "templates"
    if not templates_dir.exists():
        return ""
    snippets = []
    for f in sorted(templates_dir.glob("*.tf")):
        snippets.append(f"### {f.name}\n```hcl\n{f.read_text()}\n```")
    return "\n\n".join(snippets)


# ── Node: clarify ──────────────────────────────────────────────────────────────

def clarify(state: IacGenState) -> dict:
    """
    Extract structured requirements from the user's natural-language prompt.
    Returns a requirements dict with provider, region, compute type, etc.
    """
    log.info("clarify: extracting requirements from prompt")

    system = SystemMessage(content="""You are an AWS infrastructure architect.
Extract structured requirements from the user's infrastructure description.

Return ONLY a valid JSON object with these keys (use null for anything not mentioned):
{
  "app_name":       "short lowercase slug, e.g. my-app",
  "region":         "AWS region, default us-east-1",
  "compute":        "ecs_fargate | ec2 | lambda | null",
  "load_balancer":  "alb | nlb | null",
  "database":       "rds_postgres | rds_mysql | rds_aurora | dynamodb | null",
  "cache":          "elasticache_redis | elasticache_memcached | null",
  "storage":        "s3 | efs | null",
  "networking":     "public_only | public_private | private_only",
  "az_count":       2,
  "container_port": 8080,
  "db_name":        "name for the database, default appdb",
  "environment":    "dev | staging | prod, default dev"
}

Do not include any explanation, markdown, or text outside the JSON object.""")

    human = HumanMessage(content=state["prompt"])
    response = _llm().invoke([system, human])
    raw = response.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        requirements = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("clarify: failed to parse JSON, using defaults")
        requirements = {
            "app_name": "my-app",
            "region": "us-east-1",
            "compute": "ecs_fargate",
            "load_balancer": "alb",
            "database": "rds_postgres",
            "cache": None,
            "storage": None,
            "networking": "public_private",
            "az_count": 2,
            "container_port": 8080,
            "db_name": "appdb",
            "environment": "dev",
        }

    log.info("clarify: requirements = %s", json.dumps(requirements, indent=2))
    return {"requirements": requirements}


# ── Node: plan ────────────────────────────────────────────────────────────────

def plan(state: IacGenState) -> dict:
    """
    Produce an ordered list of AWS resources to generate, respecting
    dependency order (e.g. VPC before subnets, subnets before RDS).
    """
    req = state["requirements"]
    log.info("plan: building resource plan for %s", req.get("app_name"))

    system = SystemMessage(content="""You are a Terraform expert.
Given structured AWS infrastructure requirements, produce an ordered list of
Terraform resources to create. Order matters — dependencies must come first.

Return ONLY a valid JSON array of resource objects:
[
  {
    "type": "aws_vpc",
    "logical_name": "main",
    "file": "networking.tf",
    "description": "Main VPC with DNS enabled"
  },
  ...
]

Rules:
- Use exact Terraform resource type names (e.g. aws_ecs_cluster, aws_db_instance)
- logical_name must be a valid Terraform identifier (lowercase, underscores only)
- Group resources into these files: providers.tf, variables.tf, networking.tf,
  compute.tf, database.tf, alb.tf, iam.tf, outputs.tf
- Always include: providers.tf, variables.tf, outputs.tf
- Always include VPC + subnets + security groups when any compute or DB is present
- Include IAM role + policy attachment for ECS task execution role when compute=ecs_fargate
- Do not include a resource unless it is required by the architecture

Return only the JSON array, no explanation.""")

    human = HumanMessage(content=json.dumps(req))
    response = _llm().invoke([system, human])
    raw = response.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        resource_plan = json.loads(raw)
        if not isinstance(resource_plan, list):
            raise ValueError("Expected a list")
    except (json.JSONDecodeError, ValueError):
        log.warning("plan: failed to parse resource plan JSON")
        resource_plan = []

    log.info("plan: %d resources planned across files: %s",
             len(resource_plan),
             sorted(set(r.get("file", "unknown") for r in resource_plan)))
    return {"resource_plan": resource_plan}


# ── Node: generate ────────────────────────────────────────────────────────────

def generate(state: IacGenState) -> dict:
    """
    Generate HCL content for each .tf file in the resource plan.
    On retry, validation_errors is included so the LLM can fix specific issues.
    """
    req = state["requirements"]
    resource_plan = state["resource_plan"]
    retry_count = state["retry_count"]
    validation_errors = state.get("validation_errors", "")

    if not resource_plan:
        log.warning("generate: resource_plan is empty — skipping")
        return {"generated_files": {}}

    log.info("generate: generating HCL (attempt %d)", retry_count + 1)

    templates = _load_templates()

    # Group resources by file
    files_to_resources: dict[str, list[dict]] = {}
    for r in resource_plan:
        fname = r.get("file", "main.tf")
        files_to_resources.setdefault(fname, []).append(r)

    retry_context = ""
    if validation_errors:
        retry_context = f"""

IMPORTANT — This is retry attempt {retry_count + 1}.
The previous generation failed terraform validate with these errors:
```
{validation_errors}
```
Fix ALL of the above errors. Pay close attention to:
- Incorrect argument names (use exact names from the AWS provider schema)
- Missing required arguments
- Wrong reference syntax (must be resource_type.logical_name.attribute)
- Type mismatches"""

    system_content = f"""You are a senior DevOps engineer writing production-quality Terraform HCL for AWS.

REQUIREMENTS:
{json.dumps(req, indent=2)}

RESOURCE PLAN (ordered by dependency):
{json.dumps(resource_plan, indent=2)}

REFERENCE TEMPLATES (use these for correct argument names):
{templates if templates else "(no templates loaded)"}

RULES:
1. Generate complete, valid HCL for every file listed in the resource plan.
2. Use exact AWS provider argument names — do not invent or abbreviate.
3. Reference other resources as: resource_type.logical_name.attribute
4. variables.tf must declare all variables used anywhere.
5. outputs.tf must export: vpc_id, alb_dns_name (if ALB present), db_endpoint (if DB present).
6. providers.tf must have: terraform {{ required_providers {{ aws }} }} and provider "aws" {{ region }}.
7. Use var.region, var.app_name, var.environment throughout — never hardcode these values.
8. Security groups: ALB allows 80/443 from 0.0.0.0/0; ECS tasks allow only from ALB SG; RDS allows only from ECS SG.
9. Subnets: use cidrsubnet(var.vpc_cidr, 8, index) for clean CIDR allocation.
10. ECS task definition must specify cpu, memory, and a container definition with image, portMappings.
11. aws_db_instance: set skip_final_snapshot = true for non-prod, username from var, password from var (mark sensitive).{retry_context}

Return ONLY a JSON object mapping filename to complete HCL content:
{{
  "providers.tf": "terraform {{\\n  required_providers {{...}}\\n}}\\n...",
  "variables.tf": "variable \\"app_name\\" {{...}}\\n...",
  ...
}}

No explanation. No markdown wrapping. Only the JSON object."""

    human = HumanMessage(content=f"Generate Terraform HCL for: {req.get('app_name', 'my-app')}")
    response = _llm().invoke([SystemMessage(content=system_content), human])
    raw = response.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        generated_files = json.loads(raw)
        if not isinstance(generated_files, dict):
            raise ValueError("Expected a dict")
        # Filter to only .tf files
        generated_files = {k: v for k, v in generated_files.items() if k.endswith(".tf")}
    except (json.JSONDecodeError, ValueError) as exc:
        log.error("generate: failed to parse generated files JSON: %s", exc)
        log.debug("Raw response (first 500 chars): %s", raw[:500])
        generated_files = {}

    log.info("generate: produced %d file(s): %s", len(generated_files), list(generated_files.keys()))
    return {"generated_files": generated_files}


# ── Node: validate ────────────────────────────────────────────────────────────

def validate(state: IacGenState) -> dict:
    """
    Run terraform validate against the generated files.
    On failure, populate validation_errors and increment retry_count.
    """
    generated_files = state["generated_files"]
    retry_count = state["retry_count"]

    if not generated_files:
        log.warning("validate: no generated files to validate")
        return {
            "validation_passed": False,
            "validation_output": "No files generated.",
            "validation_errors": "No files were generated.",
            "retry_count": retry_count + 1,
        }

    log.info("validate: running terraform validate on %d files", len(generated_files))
    passed, output = validate_generated_files(generated_files)

    if passed:
        log.info("validate: PASSED")
        return {
            "validation_passed": True,
            "validation_output": output,
            "validation_errors": "",
        }
    else:
        log.warning("validate: FAILED (attempt %d/%d)", retry_count + 1, state["max_retries"])
        return {
            "validation_passed": False,
            "validation_output": output,
            "validation_errors": output,
            "retry_count": retry_count + 1,
        }


# ── Node: output ──────────────────────────────────────────────────────────────

def output(state: IacGenState) -> dict:
    """
    Write validated .tf files to the output directory.
    Sets final_status based on whether validation passed.
    """
    generated_files = state["generated_files"]
    output_dir = state["output_dir"]
    validation_passed = state["validation_passed"]

    if not generated_files:
        log.error("output: nothing to write — no files generated")
        return {"final_status": "no_plan", "written_files": []}

    written = write_terraform_files(generated_files, output_dir)
    log.info("output: wrote %d files to %s", len(written), output_dir)

    status = "success" if validation_passed else "validation_failed"
    return {"final_status": status, "written_files": written}
