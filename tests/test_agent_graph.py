import unittest
from types import SimpleNamespace

from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from app.modules.agent.graph import (
    INVALID_CITATION, NO_EVIDENCE, _conversation_messages, build_graph, validate_answer,
)


class AnswerValidationTests(unittest.TestCase):
    def test_parent_and_children_share_one_checkpointer(self):
        saver = InMemorySaver()
        settings = SimpleNamespace(
            glm_model="glm-4-flash",
            zhipu_api_key=SecretStr("test"),
            zhipu_base_url="https://open.bigmodel.cn/api/paas/v4/",
            siliconflow_api_key=SecretStr("test"),
        )
        graph = build_graph(saver, lambda: None, object(), settings)

        self.assertIs(graph.checkpointer, saver)
        self.assertIs(graph.nodes["rag"].bound.checkpointer, True)
        self.assertIs(graph.nodes["chat"].bound.checkpointer, True)

    def test_valid_regulation_citation_is_kept(self):
        state = {"intent": "rag", "sources": [{"citation_id": "one"}], "messages": [
            HumanMessage(content="问题"), AIMessage(content="依据[1]，可以办理。", id="answer-1"),
        ]}
        self.assertEqual(validate_answer(state), {"answer": "依据[1]，可以办理。"})

    def test_content_blocks_return_only_text_and_preserve_sources(self):
        sources = [{"citation_id": "one"}]
        message = AIMessage(content=[
            {"type": "text", "text": "申请条件", "index": 0},
            {"type": "text", "text": "见[1]。", "index": 1},
        ], id="answer-blocks", additional_kwargs={"sources": sources})
        update = validate_answer({"intent": "rag", "sources": sources, "messages": [message]})
        self.assertEqual(update["answer"], "申请条件见[1]。")
        self.assertEqual(update["messages"][0].content, "申请条件见[1]。")
        self.assertEqual(update["messages"][0].additional_kwargs["sources"], sources)

    def test_missing_evidence_replaces_draft(self):
        state = {"intent": "rag", "sources": [], "messages": [AIMessage(content="可以办理。", id="answer-1")]}
        update = validate_answer(state)
        self.assertEqual(update["answer"], NO_EVIDENCE)
        self.assertEqual(update["messages"][0].id, "answer-1")

    def test_out_of_range_citation_replaces_draft(self):
        state = {"intent": "rag", "sources": [{"citation_id": "one"}], "messages": [
            AIMessage(content="依据[2]，可以办理。", id="answer-1"),
        ]}
        self.assertEqual(validate_answer(state)["answer"], INVALID_CITATION)

    def test_chitchat_does_not_require_citation(self):
        state = {"intent": "chitchat", "messages": [AIMessage(content="你好", id="answer-1")]}
        self.assertEqual(validate_answer(state), {"answer": "你好"})

    def test_previous_tool_output_is_not_reused_as_new_evidence(self):
        messages = [
            HumanMessage(content="旧问题"),
            ToolMessage(content="旧法规原文", tool_call_id="call-1"),
            AIMessage(content="旧回答[1]"),
            HumanMessage(content="新问题"),
        ]
        self.assertEqual(_conversation_messages({"messages": messages}), [
            messages[0], messages[2], messages[3],
        ])


if __name__ == "__main__":
    unittest.main()
