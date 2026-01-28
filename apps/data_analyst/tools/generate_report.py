"""Generate HTML Report Tool for Data Analyst Agent."""

import os
from datetime import datetime
from typing import TYPE_CHECKING, List

from gimle.hugin.artifacts.text import Text
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def generate_report(
    title: str,
    summary: str,
    findings: List[dict],
    stack: "Stack",
) -> ToolResponse:
    """Generate an HTML report with embedded visualizations.

    Args:
        title: Report title
        summary: Executive summary of the analysis
        findings: List of findings, each with:
            - title: Finding title
            - description: Detailed description
            - chart_artifact_id: Optional artifact ID of related visualization
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with report path and artifact ID
    """
    try:
        # Get storage path for saving report
        output_dir = "./storage/data_analyst/reports"
        if stack and stack.agent.session.storage:
            storage = stack.agent.session.storage
            if hasattr(storage, "base_path") and storage.base_path:
                output_dir = str(storage.base_path / "reports")
        os.makedirs(output_dir, exist_ok=True)

        # Collect chart images from artifacts
        chart_images = {}
        if stack and stack.agent.session.storage:
            storage = stack.agent.session.storage
            for finding in findings:
                artifact_id = finding.get("chart_artifact_id")
                if artifact_id:
                    try:
                        artifact = storage.load_artifact(artifact_id)
                        # Handle both old (content attr) and new (get_content_base64) API
                        if hasattr(artifact, "get_content_base64"):
                            # New File/Image API - content stored in files
                            chart_images[artifact_id] = {
                                "content": artifact.get_content_base64(),
                                "content_type": getattr(
                                    artifact, "content_type", "image/png"
                                ),
                            }
                        elif hasattr(artifact, "content") and hasattr(
                            artifact, "content_type"
                        ):
                            # Old API fallback
                            chart_images[artifact_id] = {
                                "content": artifact.content,
                                "content_type": artifact.content_type,
                            }
                    except Exception:
                        pass  # Skip if artifact not found

        # Generate HTML
        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")
        timestamp = now.strftime("%Y%m%d_%H%M%S")

        findings_html = ""
        for i, finding in enumerate(findings, 1):
            chart_html = ""
            artifact_id = finding.get("chart_artifact_id")
            if artifact_id and artifact_id in chart_images:
                img_data = chart_images[artifact_id]
                data_url = f"data:{img_data['content_type']};base64,{img_data['content']}"
                chart_html = f"""
                <div class="chart-container">
                    <img src="{data_url}" alt="Visualization for {_escape_html(finding.get('title', 'Finding'))}" />
                </div>
                """

            findings_html += f"""
            <div class="finding">
                <h3><span class="finding-number">{i}</span>{_escape_html(finding.get('title', 'Untitled'))}</h3>
                <p>{_escape_html(finding.get('description', ''))}</p>
                {chart_html}
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(title)} - Data Analysis Report</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                         Oxygen, Ubuntu, Cantarell, sans-serif;
            margin: 0;
            padding: 0;
            background: #ffffff;
            color: #37352f;
            line-height: 1.7;
            -webkit-font-smoothing: antialiased;
        }}
        .report {{
            max-width: 720px;
            margin: 0 auto;
            padding: 60px 24px 80px;
        }}
        .header {{
            margin-bottom: 48px;
            padding-bottom: 24px;
            border-bottom: 1px solid #e8e8e8;
        }}
        .header h1 {{
            margin: 0 0 8px 0;
            font-size: 2.25em;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #191919;
        }}
        .header .date {{
            color: #9b9a97;
            font-size: 0.875em;
        }}
        .section {{
            margin-bottom: 48px;
        }}
        .section-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
        }}
        .section-header .icon {{
            font-size: 1.25em;
        }}
        .section-header h2 {{
            margin: 0;
            font-size: 1.25em;
            font-weight: 600;
            color: #37352f;
        }}
        .summary-content {{
            background: #f7f6f3;
            padding: 20px 24px;
            border-radius: 4px;
            color: #37352f;
        }}
        .summary-content p {{
            margin: 0;
        }}
        .finding {{
            margin-bottom: 32px;
            padding-bottom: 32px;
            border-bottom: 1px solid #ebebea;
        }}
        .finding:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        .finding h3 {{
            margin: 0 0 12px 0;
            font-size: 1.1em;
            font-weight: 600;
            color: #37352f;
        }}
        .finding-number {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            background: #37352f;
            color: #ffffff;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 600;
            margin-right: 10px;
        }}
        .finding p {{
            color: #6b6b6b;
            margin: 0 0 16px 0;
            font-size: 0.95em;
        }}
        .chart-container {{
            margin-top: 16px;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #e8e8e8;
        }}
        .chart-container img {{
            display: block;
            max-width: 100%;
            height: auto;
        }}
        .footer {{
            margin-top: 64px;
            padding-top: 24px;
            border-top: 1px solid #e8e8e8;
            text-align: center;
            color: #b4b4b4;
            font-size: 0.8em;
        }}
        @media (max-width: 600px) {{
            .report {{
                padding: 40px 16px 60px;
            }}
            .header h1 {{
                font-size: 1.75em;
            }}
        }}
    </style>
</head>
<body>
    <div class="report">
        <div class="header">
            <h1>{_escape_html(title)}</h1>
            <div class="date">{date_str}</div>
        </div>

        <div class="section">
            <div class="section-header">
                <span class="icon">📋</span>
                <h2>Executive Summary</h2>
            </div>
            <div class="summary-content">
                <p>{_escape_html(summary)}</p>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <span class="icon">📊</span>
                <h2>Key Findings</h2>
            </div>
            <div class="findings-list">
                {findings_html}
            </div>
        </div>

        <div class="footer">
            Generated by Data Analyst Agent
        </div>
    </div>
</body>
</html>"""

        # Save to file
        filename = f"report_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Also save as "latest.html" for easy access
        latest_path = os.path.join(output_dir, "latest.html")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Create Text artifact for display in monitor
        artifact_id = None
        if stack and stack.interactions:
            artifact = Text(
                interaction=stack.interactions[-1],
                content=html_content,
                format="html",
            )
            stack.interactions[-1].add_artifact(artifact)
            artifact_id = artifact.id

        return ToolResponse(
            is_error=False,
            content={
                "filepath": filepath,
                "latest_path": latest_path,
                "artifact_id": artifact_id,
                "num_findings": len(findings),
                "message": f"Report generated with {len(findings)} findings",
            },
        )

    except Exception as e:
        return ToolResponse(is_error=True, content={"error": str(e)})


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
