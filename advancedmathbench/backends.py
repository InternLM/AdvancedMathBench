"""Minimal chat backends: stdlib HTTP, or optional public Transformers."""
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class BackendError(RuntimeError):
    pass


def _no_credentials(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"api_key", "authorization", "password", "secret", "access_token", "headers"}:
                raise ValueError("Credentials must be environment variables, not config values")
            _no_credentials(child)
    elif isinstance(value, list):
        for child in value:
            _no_credentials(child)


def validate_config(spec):
    _no_credentials(spec)
    backend = spec.get("backend", "api")
    allowed = {"backend", "model", "generation", "base_url", "api_key_env", "timeout_s", "max_retries",
               "model_class", "dtype", "device_map", "trust_remote_code", "revision", "chat_template_kwargs"}
    if set(spec) - allowed:
        raise ValueError(f"Unknown backend config keys: {sorted(set(spec) - allowed)}")
    if not isinstance(spec.get("model"), str) or not spec["model"]:
        raise ValueError("Each configured backend needs a model")
    gen = spec.get("generation", {})
    if not isinstance(gen, dict) or any(k in gen for k in ("model", "messages", "stream", "n", "tools")):
        raise ValueError("generation must be a dict without model/messages/stream/n/tools overrides")
    if "max_tokens" in gen and "max_completion_tokens" in gen:
        raise ValueError("Use only one of max_tokens and max_completion_tokens")
    for name in ("max_tokens", "max_completion_tokens"):
        if name in gen and (type(gen[name]) is not int or gen[name] <= 0):
            raise ValueError(f"{name} must be a positive integer")
    if backend == "api":
        parts = urllib.parse.urlsplit(spec.get("base_url", ""))
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("base_url must be an HTTP(S) URL without credentials, query, or fragment")
        if not math.isfinite(float(spec.get("timeout_s", 1800))) or float(spec.get("timeout_s", 1800)) <= 0:
            raise ValueError("timeout_s must be positive and finite")
        if type(spec.get("max_retries", 2)) is not int or not 0 <= spec.get("max_retries", 2) <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        if "api_key_env" in spec and (not isinstance(spec["api_key_env"], str) or not spec["api_key_env"]):
            raise ValueError("api_key_env must name an environment variable")
    elif backend == "transformers":
        if spec.get("model_class", "qwen3_5_moe") not in ("qwen3_5_moe", "causal"):
            raise ValueError("model_class must be qwen3_5_moe or causal")
        if spec.get("dtype", "bfloat16") not in ("bfloat16", "float16", "float32"):
            raise ValueError("Unsupported dtype")
        if set(gen) - {"max_tokens", "temperature", "top_p", "top_k", "repetition_penalty"}:
            raise ValueError("Local backend supports max_tokens, temperature, top_p, top_k, repetition_penalty")
    else:
        raise ValueError("backend must be api or transformers")


class APIBackend:
    def __init__(self, spec):
        validate_config(spec)
        self.spec = spec
        self.key = None
        if spec.get("api_key_env"):
            self.key = os.environ.get(spec["api_key_env"])
            if not self.key:
                raise ValueError(f"Missing API key environment variable: {spec['api_key_env']}")
        base = spec["base_url"].rstrip("/")
        self.url = base if base.endswith("/chat/completions") else base + "/chat/completions"

    def complete(self, prompt):
        payload = {"model": self.spec["model"], "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "n": 1, **self.spec.get("generation", {})}
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        retries = self.spec.get("max_retries", 2)
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.spec.get("timeout_s", 1800)) as resp:
                    result = json.loads(resp.read())
                choice = result["choices"][0]
                msg = choice["message"]
                content = msg.get("content")
                if isinstance(content, list):
                    content = "".join(p["text"] for p in content if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str))
                if content is None:
                    content = ""
                if not isinstance(content, str):
                    raise ValueError("Nontext content")
                return {"text": content, "reasoning_content": msg.get("reasoning_content", ""),
                        "finish_reason": choice.get("finish_reason"), "usage": result.get("usage"),
                        "error": None}
            except urllib.error.HTTPError as exc:
                code = exc.code
                exc.close()
                # Do not log server bodies/URLs: they may contain credentials or prompts.
                if attempt == retries or code not in (408, 429, 500, 502, 503, 504):
                    raise BackendError(f"HTTP_{code}") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == retries:
                    raise BackendError("network_error") from None
            except (KeyError, IndexError, TypeError, ValueError):
                raise BackendError("invalid_chat_response") from None
            time.sleep(min(2 ** attempt, 4))


class TransformersBackend:
    """Optional, deliberately simple local generation; loaded only on first call."""
    def __init__(self, spec):
        validate_config(spec)
        self.spec = spec
        self.model = self.tokenizer = None

    def complete(self, prompt):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, Qwen3_5MoeForConditionalGeneration

        if self.model is None:
            kwargs = {"trust_remote_code": self.spec.get("trust_remote_code", False)}
            if self.spec.get("revision"):
                kwargs["revision"] = self.spec["revision"]
            self.tokenizer = AutoTokenizer.from_pretrained(self.spec["model"], **kwargs)
            cls = Qwen3_5MoeForConditionalGeneration if self.spec.get("model_class", "qwen3_5_moe") == "qwen3_5_moe" else AutoModelForCausalLM
            self.model = cls.from_pretrained(self.spec["model"], **kwargs,
                                            dtype=getattr(torch, self.spec.get("dtype", "bfloat16")),
                                            device_map=self.spec.get("device_map", "auto")).eval()
        text = self.tokenizer.apply_chat_template([{ "role": "user", "content": prompt}], tokenize=False,
                                                 add_generation_prompt=True, **self.spec.get("chat_template_kwargs", {}))
        inputs = self.tokenizer(text, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        gen = dict(self.spec.get("generation", {}))
        max_tokens = gen.pop("max_tokens", 65536)
        temp = gen.pop("temperature", 1.0)
        gen.update(max_new_tokens=max_tokens, do_sample=temp > 0)
        if temp > 0:
            gen["temperature"] = temp
        with torch.inference_mode():
            output = self.model.generate(**inputs, **gen)
        tokens = output[0, inputs["input_ids"].shape[1]:].tolist()
        eos = self.model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        stopped = bool(tokens and tokens[-1] in eos)
        # Preserve thinking delimiters; remove only terminal EOS, not all special tokens.
        answer_tokens = tokens[:-1] if stopped else tokens
        return {"text": self.tokenizer.decode(answer_tokens, skip_special_tokens=False), "reasoning_content": "",
                "finish_reason": "stop" if stopped or len(tokens) < max_tokens else "length",
                "usage": {"completion_tokens": len(tokens)}, "error": None}


def make_backend(spec):
    return APIBackend(spec) if spec.get("backend", "api") == "api" else TransformersBackend(spec)
