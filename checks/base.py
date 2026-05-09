from dataclasses import dataclass, field
from typing import Literal, Optional

Status = Literal["PASS", "FAIL", "UNCERTAIN"]
Verdict = Literal["ACCEPT", "REJECT", "REVIEW"]


@dataclass
class CheckResult:
    status: Status
    confidence: float  # 0.0 – 1.0
    reason: str
    extra: Optional[dict] = field(default=None)  # check-specific data (e.g. serial number)


@dataclass
class UsageRecord:
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tok: int, output_tok: int):
        self.calls += 1
        self.input_tokens += input_tok
        self.output_tokens += output_tok
