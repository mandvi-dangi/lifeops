"""Telegram delivery and deadline reminder checks for LifeOps."""
import os
import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

from database import init_db, list_tasks, reminder_was_sent, record_reminder


def send_telegram_message(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before sending reminders.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API rejected the message: {result}")


def check_and_send_reminders(today=None):
    """Send once each for 3 days before, 1 day before, and the due date."""
    init_db()
    timezone_name = os.getenv("LIFEOPS_TIMEZONE", "Asia/Kolkata")
    today = today or datetime.now(ZoneInfo(timezone_name)).date()
    sent, skipped, errors = [], [], []
    for task in list_tasks():
        if task.get("task_type") != "assignment" or task.get("status") == "Submitted" or task.get("completed"):
            continue
        due_text = task.get("due_date")
        if not due_text:
            continue
        try:
            due = date.fromisoformat(due_text[:10])
        except ValueError:
            errors.append(f"Assignment #{task['id']} has invalid due date: {due_text}")
            continue
        days_left = (due - today).days
        if days_left not in (3, 1, 0):
            continue
        if reminder_was_sent(task["id"], days_left, due_text):
            skipped.append(task["id"])
            continue
        if days_left == 3:
            headline = "📚 Assignment deadline in 3 days"
            action = "Start or continue working on it today."
        elif days_left == 1:
            headline = "⏰ Assignment due tomorrow"
            action = "Review your work and prepare the final submission."
        else:
            headline = "🚨 Assignment deadline is TODAY"
            action = "Prioritize finishing and submitting it today."
        message = (
            f"{headline}\n\n{task['title']}\n"
            f"Course: {task.get('course') or 'Not specified'}\n"
            f"Due: {due_text}\nPriority: {task.get('priority', 'medium')}\n"
            f"Estimated effort: {task.get('estimate_minutes', 30)} minutes\n\n{action}\n"
            f"Open LifeOps to update its status."
        )
        try:
            send_telegram_message(message)
            record_reminder(task["id"], days_left, due_text)
            sent.append(task["id"])
        except Exception as exc:
            errors.append(f"Assignment #{task['id']}: {exc}")
    return {"sent": sent, "already_sent": skipped, "errors": errors, "date": today.isoformat()}


if __name__ == "__main__":
    result = check_and_send_reminders()
    print(json.dumps(result, indent=2))
    if result["errors"]:
        raise SystemExit(1)
