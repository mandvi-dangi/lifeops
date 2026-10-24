import json
import os
from openai import OpenAI
from database import add_task, list_tasks, complete_task, update_task

SYSTEM = """You are LifeOps, a careful personal planning agent.
Help the user turn natural language into realistic plans. Use tools for task changes.
Always distinguish suggestions from actions actually completed. Never claim a task was saved
unless the tool succeeded. Ask a concise clarification if required information is missing.
For schedule planning, respect available_minutes and task estimates; don't schedule more work
than fits. If everything cannot fit, explain the conflict and ask what to move.
Do not make external commitments. Calendar/email integration is not enabled in this MVP.
When the user says assignment, coursework, lab report, project submission, or homework, create it as task_type=assignment and capture course/instructions when available. Do not invent missing due dates; ask for clarification or save without a date.
After tool actions, summarize exactly what changed and what remains.
"""

TOOLS = [
    {"type":"function","name":"create_task","description":"Save a new task in LifeOps storage.",
     "parameters":{"type":"object","properties":{
         "title":{"type":"string"},"due_date":{"type":["string","null"],"description":"YYYY-MM-DD or null"},
         "priority":{"type":"string","enum":["low","medium","high"]},
         "estimate_minutes":{"type":"integer","minimum":5,"maximum":600},
         "task_type":{"type":"string","enum":["task","assignment"]},
         "course":{"type":["string","null"]},
         "instructions":{"type":["string","null"]}},
      "required":["title","due_date","priority","estimate_minutes"],"additionalProperties":False}},
    {"type":"function","name":"mark_task_complete","description":"Mark an existing task complete by ID.",
     "parameters":{"type":"object","properties":{"task_id":{"type":"integer"}},"required":["task_id"],"additionalProperties":False}},
    {"type":"function","name":"reschedule_task","description":"Update a task's due date or estimate.",
     "parameters":{"type":"object","properties":{
         "task_id":{"type":"integer"},"due_date":{"type":["string","null"]},
         "estimate_minutes":{"type":["integer","null"]}},
      "required":["task_id","due_date","estimate_minutes"],"additionalProperties":False}},
]

def run_tool(name, args):
    if name == "create_task":
        task_id = add_task(args["title"], args["due_date"], args["priority"], args["estimate_minutes"],
                           task_type=args.get("task_type", "task"), course=args.get("course"), instructions=args.get("instructions"))
        return {"ok": True, "task_id": task_id, "saved_task": next(t for t in list_tasks() if t["id"] == task_id)}
    if name == "mark_task_complete":
        ok = complete_task(args["task_id"])
        return {"ok": ok, "task_id": args["task_id"], "verified": any(t["id"] == args["task_id"] and t["completed"] for t in list_tasks())}
    if name == "reschedule_task":
        fields = {}
        if args["due_date"] is not None: fields["due_date"] = args["due_date"]
        if args["estimate_minutes"] is not None: fields["estimate_minutes"] = args["estimate_minutes"]
        ok = update_task(args["task_id"], **fields)
        return {"ok": ok, "task_id": args["task_id"], "tasks_after_change": list_tasks()}
    return {"ok": False, "error": "Unknown tool"}

def respond(prompt, context):
    if not os.getenv("OPENAI_API_KEY"):
        return "AI planning is not enabled yet. Add your OpenAI API key to `.env`. You can still add, complete, and delete tasks from the dashboard."
    client = OpenAI()
    input_items = [
        {"role":"user","content": prompt},
        {"role":"user","content":"Current LifeOps context (source of truth): " + json.dumps(context, ensure_ascii=False)}
    ]
    try:
        for _ in range(5):
            response = client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=SYSTEM,
                input=input_items,
                tools=TOOLS,
                parallel_tool_calls=False
            )
            input_items += response.output
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                return response.output_text or "I couldn't produce a response. Please try again."
            for call in calls:
                try:
                    args = json.loads(call.arguments)
                    result = run_tool(call.name, args)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                input_items.append({"type":"function_call_output","call_id":call.call_id,"output":json.dumps(result, ensure_ascii=False)})
        return "I stopped after several tool steps to avoid an execution loop. Please review your tasks and try a narrower request."
    except Exception as exc:
        return f"I couldn't reach the AI service. Check your API key/model and try again. Details: {exc}"
