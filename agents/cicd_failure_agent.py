import json
from typing import Dict, Any, List

from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Data, Command
from schemas.cicd_log import CICDLogEntry
from vector_store import VectorStore
from predictor import FailurePredictor
from services.llm import BedrockAnthropicLLM

class CICDFailureAgent(AgentProtocol):
    def __init__(self):
        # 1) Claude LLM client
        self.llm = BedrockAnthropicLLM(region_name="us-east-1")

        # 2) FAISS index for retrieval‐augmented diagnosis
        self.store = VectorStore()
        labeled = json.load(open("data/labeled_logs.json", encoding="utf-8"))
        entries: List[CICDLogEntry] = [
            CICDLogEntry.model_validate(d) for d in labeled
        ]
        self.store.upsert_entries(entries)

        # 3) Supervised predictor training for failure risk
        self.predictor = FailurePredictor()
        self.predictor.train(entries)

    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        # A) Extract the new ERROR log line
        new_log = messages["messages"][-1]["content"]

        # B) Compute calibrated failure risk (0.0–1.0)
        risk = self.predictor.predict_risk(new_log)

        # C) Retrieve top‐5 similar past entries
        neighbors = self.store.query(new_log, k=5)

        # D) Force the canonical root cause from your labels
        primary_cause = neighbors[0].get("root_cause") or "Unknown"

        # E) Build a prompt asking only for next‐steps
        system = (
            "You’re a concise DevOps expert. Given past CI/CD logs with statuses and root causes, "
            "suggest exactly 2 bullet-point next steps to resolve this new ERROR."
            # "You’re a concise DevOps expert. "
            # "Given past logs with statuses and root causes, and a new ERROR line, "
            # "output valid JSON with three keys:\n"
            # "  • risk: probability of failure as a float 0–1\n"
            # "  • root_causes: array of up to 3 objects {cause:string, confidence:float}\n"
            # "  • next_steps: array of 2–3 concise bullet-step strings\n"
            # "No extra keys or free text—just the JSON object."
        )
        context = "\n\n".join(
            f"LOG: {n['message']}\n"
            f"STATUS: {n['status']}\n"
            f"ROOT_CAUSE: {n['root_cause'] or 'unknown'}"
            for n in neighbors
        )
        user_content = (
            f"{context}\n\n"
            f"NEW LOG: {new_log}\n\n"
            "QUESTION: What next steps should I take?"
        )

        # F) Invoke Claude for remediation steps only
        answer = self.llm.invoke(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system,
            model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
            temperature=0.0,
            max_tokens=200,
            stop_sequences=["\nHuman:"],
        )

        # G) Assemble the final content
        header = (
            f"• FAILURE RISK: {risk*100:.0f}%. "
            f"• ROOT CAUSE: {primary_cause}. "
            "• NEXT STEPS: "
        )
        # indent each bullet returned by Claude
        steps = "".join(f"  {line}\n" for line in answer.strip().splitlines())
        final = header + steps

        # H) Build optional GitHub-CLI suggestions
        cmds: List[Command] = []
        if "unit test" in primary_cause.lower():
            cmds.append(Command(
                command="gh run list --workflow ci.yml --limit 5",
                execute=False
            ))
            cmds.append(Command(
                command="gh run rerun <run-id>",
                execute=False
            ))
        elif "Docker image" in primary_cause.lower():
            cmds.append(Command(
                command="docker build -t image_name .",
                execute=False
            ))
            cmds.append(Command(
                command="docker push image_name .",
                execute=False
            ))
        elif "network" in primary_cause.lower():
            cmds.append(Command(
                command="ping -c 4 registry.example.com",
                execute=False
            ))
            cmds.append(Command(
                command="curl -v https://registry.example.com/v2/",
                execute=False))

        # I) Return both human‐readable content and actionable cmds
        return AgentMessage(
            content=final,
            data=Data(cmds=cmds)
        )
