from mikoshi.agents.research import ResearchAgentPlugin


class DeepResearchAgent(ResearchAgentPlugin):
    default = False
    name = "R3-534-RCH-3R"
    provider_id = "llamactl"
    model_id = "Qwen3_6-35B-A3B"
    tool_servers = ["web", "workspace", "time"]
    max_iterations = 20
    max_outer_iterations = 20
    max_inner_iterations = 50
    system_prompt = ""