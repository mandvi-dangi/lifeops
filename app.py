import os
from datetime import date
import streamlit as st
from dotenv import load_dotenv
from database import init_db, list_tasks, add_task, complete_task, delete_task, update_task
from agent import respond
from speech import transcribe_audio, synthesize_speech
from assignment_files import extract_assignment_details

load_dotenv()
for secret_name in ("OPENAI_API_KEY", "OPENAI_MODEL", "SARVAM_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LIFEOPS_TIMEZONE"):
    try:
        secret_value = st.secrets.get(secret_name)
        if secret_value and not os.getenv(secret_name):
            os.environ[secret_name] = str(secret_value)
    except Exception:
        pass

st.set_page_config(page_title="LifeOps — Assignment Assistant", page_icon="🧭", layout="wide")
init_db()
st.title("🧭 LifeOps")
st.caption("Your personal assignment deadline assistant — capture tasks, track submissions, and receive Telegram reminders.")

missing = [name for name in ("OPENAI_API_KEY", "SARVAM_API_KEY") if not os.getenv(name)]
if missing:
    st.info("Optional features need configuration: " + ", ".join(missing) + ". Manual assignment tracking still works.")

with st.sidebar:
    st.header("➕ Quick assignment capture")
    with st.form("manual_assignment", clear_on_submit=True):
        title = st.text_input("Assignment name", placeholder="e.g. SVM Lab Report")
        course = st.text_input("Course / subject", placeholder="e.g. Machine Learning")
        has_deadline = st.checkbox("I know the deadline", value=True)
        due = st.date_input("Deadline", value=date.today()) if has_deadline else None
        priority = st.selectbox("Priority", ["high", "medium", "low"], index=1)
        minutes = st.number_input("Estimated work (minutes)", min_value=5, max_value=600, value=60, step=15)
        instructions = st.text_area("Notes / submission instructions", height=70)
        submitted = st.form_submit_button("Save assignment", use_container_width=True)
        if submitted:
            if not title.strip():
                st.error("Enter an assignment name.")
            else:
                task_id = add_task(title.strip(), due.isoformat() if due else None, priority, int(minutes),
                                   task_type="assignment", course=course.strip() or None, instructions=instructions.strip() or None)
                st.success(f"Assignment saved (#{task_id}).")
                st.rerun()
    st.divider()
    st.subheader("Today's study time")
    available = st.number_input("Free time (minutes)", min_value=15, max_value=1440, value=180, step=15)

capture_tab, assignment_tab, task_tab, assistant_tab = st.tabs(["📥 Upload brief", "🎓 Assignments", "✅ Other tasks", "🎙️ Voice assistant"])

with capture_tab:
    st.subheader("Create an assignment from a file")
    st.write("Upload an assignment brief. LifeOps extracts likely details; **review every field before saving**. The original file is processed for extraction and is not stored by this MVP.")
    uploaded = st.file_uploader("Assignment brief", type=["pdf", "docx", "txt", "md", "csv", "png", "jpg", "jpeg", "webp"], key="assignment_upload")
    if uploaded and st.button("Extract assignment details", type="primary"):
        with st.spinner("Reading the brief and extracting assignment details…"):
            try:
                st.session_state["extracted_assignment"] = extract_assignment_details(uploaded)
                st.session_state["extracted_assignment_filename"] = uploaded.name
                st.success("Details extracted. Review and confirm below.")
            except Exception as exc:
                st.error(f"Could not extract details: {exc}")
    details = st.session_state.get("extracted_assignment")
    if details:
        st.markdown("**Review extracted details**")
        with st.form("review_extracted_assignment"):
            f_title = st.text_input("Assignment title", value=str(details.get("title") or ""))
            f_course = st.text_input("Course", value=str(details.get("course") or ""))
            f_has_date = st.checkbox("Deadline identified / known", value=bool(details.get("due_date")))
            parsed_date = None
            if details.get("due_date"):
                try:
                    parsed_date = date.fromisoformat(str(details["due_date"])[:10])
                except ValueError:
                    parsed_date = None
            f_due = st.date_input("Deadline", value=parsed_date or date.today()) if f_has_date else None
            p_opts = ["high", "medium", "low"]
            p_default = details.get("priority", "medium")
            f_priority = st.selectbox("Priority", p_opts, index=p_opts.index(p_default) if p_default in p_opts else 1)
            f_minutes = st.number_input("Estimated work (minutes)", min_value=5, max_value=600, value=int(details.get("estimate_minutes") or 60), step=15)
            f_instructions = st.text_area("Instructions / notes", value=str(details.get("instructions") or ""), height=100)
            save_extracted = st.form_submit_button("Confirm and save assignment", type="primary")
            if save_extracted:
                if not f_title.strip():
                    st.error("Assignment title is required.")
                else:
                    task_id = add_task(f_title.strip(), f_due.isoformat() if f_due else None, f_priority, int(f_minutes),
                                       task_type="assignment", course=f_course.strip() or None,
                                       instructions=f_instructions.strip() or None,
                                       source_file=st.session_state.get("extracted_assignment_filename"))
                    st.session_state.pop("extracted_assignment", None)
                    st.session_state.pop("extracted_assignment_filename", None)
                    st.success(f"Assignment saved (#{task_id}).")
                    st.rerun()

with assignment_tab:
    assignments = list_tasks(task_type="assignment")
    open_assignments = [t for t in assignments if t.get("status") != "Submitted" and not t["completed"]]
    submitted_assignments = [t for t in assignments if t.get("status") == "Submitted" or t["completed"]]
    m1, m2, m3 = st.columns(3)
    m1.metric("Open assignments", len(open_assignments))
    m2.metric("Submitted", len(submitted_assignments))
    overdue = [t for t in open_assignments if t.get("due_date") and t["due_date"] < date.today().isoformat()]
    m3.metric("Overdue", len(overdue))
    if not assignments:
        st.info("Add an assignment from the sidebar, upload its brief, or capture it by voice.")
    for task in assignments:
        with st.container(border=True):
            left, right = st.columns([5, 2])
            with left:
                st.markdown(f"**{task['title']}**")
                st.caption(f"Course: {task.get('course') or 'Not specified'} · Priority: {task['priority']} · Estimated effort: {task['estimate_minutes']} min")
                if task.get("due_date"):
                    days = (date.fromisoformat(task["due_date"][:10]) - date.today()).days
                    if task.get("status") == "Submitted" or task["completed"]:
                        st.caption(f"Due: {task['due_date']} · ✅ Submitted")
                    elif days < 0:
                        st.error(f"Overdue by {-days} day(s) · Due {task['due_date']}")
                    elif days == 0:
                        st.warning(f"Due TODAY · {task['due_date']}")
                    else:
                        st.caption(f"Due: {task['due_date']} · {days} day(s) left")
                else:
                    st.caption("No deadline set — add one to enable deadline reminders.")
                if task.get("instructions"):
                    with st.expander("Instructions / notes"):
                        st.write(task["instructions"])
                if task.get("submitted_at"):
                    st.caption(f"Submission recorded: {task['submitted_at']}")
            with right:
                status_options = ["Not started", "In progress", "Submitted"]
                current = task.get("status", "Not started")
                selected = st.selectbox("Status", status_options, index=status_options.index(current) if current in status_options else 0, key=f"status_{task['id']}")
                if st.button("Update status", key=f"update_status_{task['id']}", use_container_width=True):
                    update_task(task["id"], status=selected)
                    st.rerun()
                if st.button("Delete", key=f"delete_assignment_{task['id']}", use_container_width=True):
                    delete_task(task["id"])
                    st.rerun()

with task_tab:
    tasks = list_tasks(task_type="task")
    st.metric("Other open tasks", sum(not t["completed"] for t in tasks))
    if not tasks:
        st.info("Non-assignment tasks created by the voice agent will appear here.")
    for task in tasks:
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"**{task['title']}**")
                st.caption(f"Priority: {task['priority']} · Estimate: {task['estimate_minutes']} min" + (f" · Due: {task['due_date']}" if task.get("due_date") else ""))
                if task["completed"]:
                    st.caption("✅ Completed")
            with c2:
                if not task["completed"] and st.button("Done", key=f"done_{task['id']}"):
                    complete_task(task["id"])
                    st.rerun()
                if st.button("Delete", key=f"del_{task['id']}"):
                    delete_task(task["id"])
                    st.rerun()

with assistant_tab:
    st.subheader("🎙️ Voice-to-action")
    st.write('Try: “Add my Machine Learning assignment due next Friday, high priority, about two hours.” Review the transcript before sending it.')
    try:
        from streamlit_mic_recorder import mic_recorder
        audio = mic_recorder(start_prompt="Start recording", stop_prompt="Stop recording", key="lifeops_mic", use_container_width=True)
    except Exception as exc:
        audio = None
        st.error(f"Microphone component could not load: {exc}")
    if audio and audio.get("bytes"):
        st.audio(audio["bytes"], format="audio/wav")
        if st.button("Transcribe with Sarvam", type="primary", use_container_width=True):
            if not os.getenv("SARVAM_API_KEY"):
                st.error("SARVAM_API_KEY is missing.")
            else:
                with st.spinner("Sarvam is transcribing your audio…"):
                    try:
                        transcript, language = transcribe_audio(audio["bytes"])
                        st.session_state["lifeops_transcript"] = transcript
                        st.session_state["lifeops_language"] = language or "unknown"
                    except Exception as exc:
                        st.error(f"Transcription failed. Check the Sarvam key, credits, and audio format. Details: {exc}")
    transcript = st.session_state.get("lifeops_transcript", "")
    if transcript:
        edited_transcript = st.text_area("Review / edit transcript", value=transcript, key="lifeops_transcript_editor")
        st.caption(f"Detected language: {st.session_state.get('lifeops_language', 'unknown')}")
        if st.button("Send transcript to LifeOps", use_container_width=True):
            if not edited_transcript.strip():
                st.warning("Transcript is empty.")
            elif not os.getenv("OPENAI_API_KEY"):
                st.error("OPENAI_API_KEY is missing.")
            else:
                context = {"today": date.today().isoformat(), "available_minutes": int(available), "tasks": list_tasks()}
                with st.spinner("LifeOps is reasoning and managing tasks…"):
                    answer = respond(edited_transcript.strip(), context)
                st.session_state.setdefault("voice_history", []).append({"transcript": edited_transcript.strip(), "answer": answer})
                st.session_state.pop("lifeops_transcript", None)
                st.rerun()
    history = st.session_state.get("voice_history", [])
    for idx in range(len(history) - 1, -1, -1):
        item = history[idx]
        with st.container(border=True):
            st.markdown(f"**You said:** {item['transcript']}")
            st.markdown(f"**LifeOps:** {item['answer']}")
            if st.button("🔊 Speak response", key=f"speak_response_{idx}"):
                if not os.getenv("SARVAM_API_KEY"):
                    st.error("SARVAM_API_KEY is missing.")
                else:
                    with st.spinner("Sarvam is generating speech…"):
                        try:
                            st.session_state[f"lifeops_spoken_audio_{idx}"] = synthesize_speech(item["answer"])
                        except Exception as exc:
                            st.error(f"Speech generation failed: {exc}")
            spoken_audio = st.session_state.get(f"lifeops_spoken_audio_{idx}")
            if spoken_audio:
                st.audio(spoken_audio, format="audio/wav")

st.divider()
st.caption("Reminders are sent by the separate scheduled reminder worker, not by keeping this page open. Configure Telegram credentials and deploy the worker on a scheduler with access to the same persistent database.")
