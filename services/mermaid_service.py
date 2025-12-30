import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Tuple

from utils.safe_logging import safe_log_exception, safe_log_warning

logger = logging.getLogger(__name__)


def mermaid_to_pdf_bytes(
    diagram: str,
    theme: str | None = None,
    background: str | None = None,
    scale: float | int | None = None,
) -> bytes:
    """Render Mermaid diagram text to PDF bytes using Mermaid CLI (mmdc).

    Raises subprocess.CalledProcessError on CLI failures or Exception on IO errors.
    """
    if not isinstance(diagram, str) or not diagram.strip():
        raise ValueError("diagram must be a non-empty string")

    # Determine Mermaid CLI path (mmdc only; no fallback)
    mmdc_path = shutil.which("mmdc")
    if not mmdc_path:
        raise FileNotFoundError(
            "'mmdc' not found in PATH. Please install @mermaid-js/mermaid-cli."
        )
    mmdc_args: list[str] = [mmdc_path]

    # In container, use the no-sandbox Puppeteer config if present
    is_container = Path("/.dockerenv").exists() or os.getenv("KUBERNETES_SERVICE_HOST") is not None
    container_puppeteer_cfg = Path("/app/puppeteer-config.json")
    if is_container:
        if container_puppeteer_cfg.exists():
            mmdc_args.extend(["--puppeteerConfigFile", str(container_puppeteer_cfg)])
        else:
            safe_log_warning(logger, "/app/puppeteer-config.json not found inside container; continuing without it")
    if isinstance(theme, str) and theme:
        mmdc_args.extend(["-t", theme])
    if isinstance(background, str) and background:
        mmdc_args.extend(["-b", background])
    if isinstance(scale, (int, float)) and scale:
        mmdc_args.extend(["-s", str(scale)])

    with tempfile.TemporaryDirectory() as tmpdir:
        mmd_path = Path(tmpdir) / "diagram.mmd"
        pdf_path = Path(tmpdir) / "diagram.pdf"
        mmd_path.write_text(diagram, encoding="utf-8")

        cmd = mmdc_args + ["-i", str(mmd_path), "-o", str(pdf_path)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            # Re-raise with original context; stderr will be attached to the exception
            raise

        pdf_bytes = pdf_path.read_bytes()
        return pdf_bytes


def extract_mermaid_blocks(text: str) -> list[str]:
    """Find ```mermaid ...``` code blocks and return their inner code.

    Matches fenced code blocks with the language identifier `mermaid`.
    """
    if not isinstance(text, str) or "```" not in text:
        return []
    pattern = r"```mermaid\s+([\s\S]*?)```"
    return [m.strip() for m in re.findall(pattern, text, flags=re.IGNORECASE)]


def attach_pdfs_from_mermaid(
    content: Any,
    data: Any,
    logger_override: logging.Logger | None = None,
) -> Tuple[Any, Any]:
    """Temporarily disabled: do not attach diagrams to responses.

    Returns content and data unchanged.
    """
    from utils.safe_logging import safe_log_info
    log = logger_override or logger
    safe_log_info(log, "Mermaid attachments are currently disabled; skipping rendering and URL generation")
    return content, data

    # --- Previous implementation (kept for future re-enable) ---
    try:
        if isinstance(content, str):
            content_text = content
        elif isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(str(block))
            content_text = "\n".join(parts)
        else:
            content_text = str(content)

        blocks = extract_mermaid_blocks(content_text)
        if blocks:
            # Build url_configs with data: URLs for PDFs
            url_configs = [] if not isinstance(data, dict) else list(data.get("url_configs", []))
            for idx, code in enumerate(blocks, start=1):
                try:
                    pdf = mermaid_to_pdf_bytes(code)
                    b64_pdf = __import__("base64").b64encode(pdf).decode("ascii")
                    url_configs.append({
                        "url": f"data:application/pdf;base64,{b64_pdf}",
                        "description": f"Rendered Mermaid diagram {idx}",
                    })
                except Exception:
                    safe_log_exception(log, "Failed to render Mermaid block to PDF")
            if isinstance(data, dict):
                # Do not attach binary files; only provide URL configs
                data["url_configs"] = url_configs
                data.setdefault("executed_cmds", [])
                # Remove files key if exists for cleanliness
                if "files" in data:
                    try:
                        del data["files"]
                    except Exception:
                        pass
            else:
                data = {
                    "url_configs": url_configs,
                    "executed_cmds": [],
                }
            if isinstance(content, str):
                content = (content + "\n\nI have generated an architecture diagram and provided it as a URL.").strip()
    except Exception:
        safe_log_exception(log, "Mermaid detection/attachment failed")

    return content, data


