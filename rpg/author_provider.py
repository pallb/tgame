"""Model-assisted drafting for prompt files the author explicitly chooses to send."""

import json
import os
import re
from http.client import HTTPConnection, HTTPSConnection, HTTPException


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"payload_json": {"type": "string"}},
    "required": ["payload_json"],
    "additionalProperties": False,
}
INSTRUCTIONS = (
    "Follow the authoring request and return the requested JSON object serialized inside payload_json. "
    "Do not include Markdown, executable code, or prose outside that JSON."
)


def request_json(host: str, path: str, headers: dict, payload: dict) -> dict:
    connection = HTTPSConnection(host, timeout=90)
    try:
        connection.request("POST", path, json.dumps(payload),
                           {"Content-Type": "application/json", **headers})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"Cloud provider returned HTTP {response.status}. Check the model and credentials.")
        data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("Cloud proposal response exceeded 1 MB.")
        return json.loads(data)
    except HTTPException as error:
        raise ValueError(f"Cloud response failed: {error}") from error
    finally:
        connection.close()


def request_ollama(path: str, payload: dict | None = None) -> dict:
    connection = HTTPConnection("127.0.0.1", 11434, timeout=180 if payload else 5)
    try:
        if payload is None:
            connection.request("GET", path)
        else:
            connection.request("POST", path, json.dumps(payload), {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"Local Ollama returned HTTP {response.status} for {path}.")
        data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("Local Ollama response exceeded 1 MB.")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Invalid local Ollama response.")
        return result
    except ConnectionRefusedError as error:
        raise ValueError("Start Ollama locally on 127.0.0.1:11434 and try again.") from error
    except HTTPException as error:
        raise ValueError(f"Invalid local Ollama response: {error}") from error
    finally:
        connection.close()


def prepared_revision(prompt: str) -> dict | None:
    try:
        fields = json.loads(prompt.rsplit("\n\n", 1)[-1])
    except ValueError:
        return None
    if (isinstance(fields, dict) and set(fields) == {"base_sha256", "locked_paths", "sections"}
            and isinstance(fields["sections"], dict) and isinstance(fields["base_sha256"], str)
            and re.fullmatch(r"[a-f0-9]{64}", fields["base_sha256"])):
        return fields
    return None


def bind_revision(answer: dict, prepared: dict) -> dict:
    from .author_revisions import at, pointer

    edits = answer.get("edits")
    if not isinstance(edits, list) or not edits:
        raise ValueError("The local model did not return revision edits.")
    scopes = sorted(((pointer(path), value) for path, value in prepared["sections"].items()),
                    key=lambda item: -len(item[0]))
    bound = []
    for edit in edits:
        if not isinstance(edit, dict) or not {"path", "after"} <= edit.keys():
            raise ValueError("The local model returned an edit without a path or replacement value.")
        keys = pointer(edit["path"])
        for scope, snapshot in scopes:
            if scope == keys[:len(scope)]:
                bound.append({"path": edit["path"], "before": at(snapshot, keys[len(scope):]), "after": edit["after"]})
                break
        else:
            raise ValueError(f"The local proposal contains an edit outside the prepared scope: {edit['path']}")
    return {"proposal_schema": 1, "base_sha256": prepared["base_sha256"], "edits": bound}


def suggest_ollama(model: str, prompt: str, context: int) -> dict:
    if not 4096 <= context <= 32768:
        raise ValueError("Ollama authoring context must be between 4096 and 32768 tokens.")
    tag = model.rsplit("/", 1)[-1]
    if ":" not in tag:
        model += ":latest"
    if model.casefold().endswith((":cloud", "-cloud")):
        raise ValueError("Use an installed local Ollama model for authoring.")
    models = request_ollama("/api/tags").get("models", [])
    matches = [entry for entry in models if entry.get("name") == model or entry.get("model") == model]
    if not matches:
        raise ValueError(f"Model {model} is not installed locally. Install a local model in Ollama first.")
    if any(item.get("remote_model") or item.get("remote_host") for item in matches):
        raise ValueError(f"Model {model} points to a remote Ollama provider. Choose an installed local model.")
    prepared = prepared_revision(prompt)
    instruction = "Return exactly the JSON object requested by the author. Do not wrap it in Markdown."
    if prepared is not None:
        instruction = ("For a revision, return only a JSON object with an edits array. Each edit is an object "
                       "with path and after. Keep paths within the supplied sections and leave locked fields unchanged. "
                       "The authoring tool will supply the fingerprint and before values. Do not use Markdown.")
        prompt = prompt + "\nFor this local run return only edits with path and after. The tool fills in the remaining fields."
    response = request_ollama("/api/chat", {
        "model": model,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": prompt},
        ],
        "stream": False, "format": "json", "think": False, "keep_alive": 0,
        "options": {"num_ctx": context, "num_predict": min(4096, context // 2), "temperature": 0.0},
    })
    if response.get("remote_model") or response.get("remote_host"):
        raise ValueError("Ollama reported a remote response.")
    if response.get("done") is not True or response.get("done_reason") == "length":
        raise ValueError("Local Ollama did not finish the proposal. Try a shorter prompt or a larger context.")
    proposal = json.loads(response["message"]["content"])
    if not isinstance(proposal, dict):
        raise ValueError("Expected the local model to return an author project or proposal as a JSON object.")
    return bind_revision(proposal, prepared) if prepared else proposal


def suggest(provider: str, model: str, prompt: str, *, context: int | None = None) -> dict:
    if provider == "ollama":
        return suggest_ollama(model, prompt, context if context is not None else 8192)
    if context is not None:
        raise ValueError("--context applies only to --provider ollama.")
    variable = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}[provider]
    key = os.getenv(variable)
    if not key:
        raise ValueError(f"Set {variable} in the environment to use {provider}.")
    if provider == "openai":
        response = request_json(
            "api.openai.com", "/v1/responses", {"Authorization": f"Bearer {key}"},
            {"model": model, "input": prompt, "instructions": INSTRUCTIONS, "store": False,
             "max_output_tokens": 8000, "text": {"format": {"type": "json_schema", "name": "author_proposal",
                                                          "strict": True, "schema": RESPONSE_SCHEMA}}},
        )
        if response.get("status") != "completed":
            raise ValueError("OpenAI did not complete the proposal.")
        blocks = [block for item in response.get("output", [])
                  for block in item.get("content", []) if block.get("type") == "output_text"]
    else:
        response = request_json(
            "api.anthropic.com", "/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": model, "system": INSTRUCTIONS, "max_tokens": 8000,
             "messages": [{"role": "user", "content": prompt}],
             "output_config": {"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}}},
        )
        if response.get("stop_reason") != "end_turn":
            raise ValueError("Claude did not complete the proposal.")
        blocks = [block for block in response.get("content", []) if block.get("type") == "text"]
    if len(blocks) != 1:
        raise ValueError("Cloud provider returned no usable structured proposal.")
    wrapper = json.loads(blocks[0]["text"])
    if not isinstance(wrapper, dict) or set(wrapper) != {"payload_json"}:
        raise ValueError("Cloud proposal was missing the structured envelope.")
    output = json.loads(wrapper["payload_json"])
    if not isinstance(output, dict):
        raise ValueError("Expected a JSON object inside the cloud proposal.")
    return output
