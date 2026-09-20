import os
import sys

def main():
    src_file = "agent-console.html"
    if not os.path.exists(src_file):
        print(f"Error: {src_file} does not exist.")
        sys.exit(1)

    with open(src_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Extract CSS
    s_tag = "<style>"
    e_tag = "</style>"
    s_pos = content.find(s_tag)
    e_pos = content.find(e_tag)
    if s_pos == -1 or e_pos == -1:
        print("Error: Could not find <style> tags")
        sys.exit(1)
    css_content = content[s_pos + len(s_tag):e_pos].strip()

    # 2. Extract JS
    sc_tag = "<script>"
    esc_tag = "</script>"
    sc_pos = content.find(sc_tag)
    esc_pos = content.rfind(esc_tag)
    if sc_pos == -1 or esc_pos == -1:
        print("Error: Could not find <script> tags")
        sys.exit(1)
    js_content = content[sc_pos + len(sc_tag):esc_pos].strip()

    # 3. Construct HTML
    before_style = content[:s_pos]
    between_style_script = content[e_pos + len(e_tag):sc_pos]
    after_script = content[esc_pos + len(esc_tag):]

    html_content = (
        before_style
        + '<link rel="stylesheet" href="styles.css">\n'
        + between_style_script
        + '<script src="app.js"></script>\n'
        + after_script
    )

    # 4. Apply wiring fixes to JS
    # Fix 4a: Add approve() function and wire approve / modify / reject to call /api/runs/{id}/approve
    target_control_resume = """  if (act==='approve'||act==='modify'||act==='reject'){
    control('resume',{approval_status:act==='approve'?'approved':act});
    S.status='running'; schedule();
  }"""

    replacement_control_resume = """  if (act==='approve'||act==='modify'||act==='reject'){
    approve(act==='approve'?'approved':act);
  }"""

    if target_control_resume not in js_content:
        print("Warning: target_control_resume exact match not found in JS, searching substring...")
    else:
        js_content = js_content.replace(target_control_resume, replacement_control_resume)

    # Fix 4b: Define approve() function right above control()
    approve_fn = """async function approve(approval_status){
  if (!S.runId) return toast('No run selected','err');
  if (S.demo)  return toast('Demo replay — controls are inert here');
  try {
    const res = await api(`/api/runs/${S.runId}/approve`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({approval_status})
    });
    toast(`Sent decision: ${approval_status}`, 'ok');
    S.status = 'running';
    schedule();
  } catch(e) {
    toast(`Approval failed: ${e.message}`, 'err');
  }
}
"""
    target_control_def = "async function control(action, extra){"
    if target_control_def in js_content:
        js_content = js_content.replace(target_control_def, approve_fn + target_control_def)
    else:
        print("Warning: target_control_def not found in JS")

    # Fix 4c: Normalize status so 'paused_for_approval' is treated as 'awaiting_approval'
    # In notices():
    old_notices_gate = "if (S.status === 'awaiting_approval'){"
    new_notices_gate = "if (S.status === 'awaiting_approval' || S.status === 'paused_for_approval'){"
    js_content = js_content.replace(old_notices_gate, new_notices_gate)

    # In loadRun():
    old_load_status = "S.status = meta.status || 'completed';"
    new_load_status = "S.status = (meta.status === 'paused_for_approval' ? 'awaiting_approval' : meta.status) || 'completed';"
    js_content = js_content.replace(old_load_status, new_load_status)

    # In connect condition in loadRun():
    old_conn = "if (S.status==='running'||S.status==='awaiting_approval'){ connect(id); startTicker(); }"
    new_conn = "if (S.status==='running'||S.status==='awaiting_approval'||S.status==='paused_for_approval'){ connect(id); startTicker(); }"
    js_content = js_content.replace(old_conn, new_conn)

    # In ingest():
    old_evt_status = "if (evt.status) S.status = evt.status;"
    new_evt_status = "if (evt.status) S.status = (evt.status === 'paused_for_approval' ? 'awaiting_approval' : evt.status);"
    js_content = js_content.replace(old_evt_status, new_evt_status)

    # Write files to web/
    os.makedirs("web", exist_ok=True)
    with open("web/styles.css", "w", encoding="utf-8") as f:
        f.write(css_content + "\n")
    with open("web/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    with open("web/app.js", "w", encoding="utf-8") as f:
        f.write(js_content + "\n")

    print(f"Successfully deployed UI to web/:")
    print(f"  web/styles.css: {len(css_content)} chars")
    print(f"  web/index.html: {len(html_content)} chars")
    print(f"  web/app.js:     {len(js_content)} chars")

if __name__ == "__main__":
    main()
