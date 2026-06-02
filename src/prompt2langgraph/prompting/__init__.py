from prompt2langgraph.prompting.config import PromptPlannerConfig, load_prompt_planner_config
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
from prompt2langgraph.prompting.planner import (
    PromptPlanRequest,
    PromptPlanResult,
    build_model_client,
    generate_plan_text,
    plan_prompt_to_workflow_spec,
)
from prompt2langgraph.prompting.skill_planner import (
    SkillPlanRequest,
    SkillPlanResult,
    build_skill_plan_prompt,
    generate_skill_plan_text,
    plan_skill_to_workflow_spec,
)

# PromptPlannerConfig and load_prompt_planner_config are deprecated;
# use prompt2langgraph.llm.config.LLMConfig and load_llm_config instead.


def __getattr__(name: str):
    if name in {
        "PlanningPipelineResult",
        "PlanningStageStatus",
        "RepairAttemptRecord",
        "plan_prompt",
        "plan_skill",
    }:
        from prompt2langgraph.prompting import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PromptPlanRequest",
    "PromptPlanResult",
    "PromptPlannerConfig",
    "PlanningPipelineResult",
    "PlanningStageStatus",
    "RepairAttemptRecord",
    "build_model_client",
    "generate_plan_text",
    "load_prompt_planner_config",
    "parse_prompt_plan_text",
    "plan_prompt",
    "plan_prompt_to_workflow_spec",
    "plan_skill",
    "SkillPlanRequest",
    "SkillPlanResult",
    "build_skill_plan_prompt",
    "generate_skill_plan_text",
    "plan_skill_to_workflow_spec",
]
