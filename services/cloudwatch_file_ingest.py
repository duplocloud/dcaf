import re
from datetime import datetime
from typing import List
from schemas.cicd_log import CICDLogEntry

# A simple regex for lines like: "2024-05-07 21:53:45,769 [WARN] message…"
LOG_LINE_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*(?P<level>ERROR|WARN|INFO)\s+(?P<msg>.*)"
)

def parse_cloudwatch_file(
    path: str,
    log_group: str = "local-file",
    stream: str = "exported-stream"
) -> List[CICDLogEntry]:
    entries: List[CICDLogEntry] = []

    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue

            m = LOG_LINE_RE.match(raw)
            if m:
                ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S,%f")
                level = m.group("level")
                msg = m.group("msg")
            else:
                # fallback: treat the entire line as message; timestamp=now
                ts = datetime.utcnow()
                msg = raw
                level = "ERROR" if "ERROR" in raw else "INFO"

            status = "FAILED" if level == "ERROR" else "SUCCEEDED"
            entry = CICDLogEntry(
                timestamp=ts,
                message=msg,
                stream=stream,
                log_group=log_group,
                status=status,
                root_cause=None,  # label later for failures
            )
            entries.append(entry)

    return entries
