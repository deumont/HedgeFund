from backend.intelligence import AgentDecision


def test_agent_response_schema_requires_every_field_including_nested_sizing():
    # OpenAI strict output rejects optional object fields before any analysis runs.
    def check(node):
        if isinstance(node,dict):
            if node.get('type')=='object':
                assert node.get('additionalProperties') is False
                assert set(node.get('required',[]))==set(node.get('properties',{}))
            for value in node.values():check(value)
        elif isinstance(node,list):
            for value in node:check(value)
    check(AgentDecision.model_json_schema())
