"""Model loading and greedy generation, shared by the service and the evaluation script."""
import os

from prompt import build_prompt


def cpu_limit():
    """CPU cores this process may use (cgroup quota when running in a container)."""
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if quota != "max":
            return max(1, round(int(quota) / int(period)))
    except (OSError, ValueError):
        pass
    try:
        quota = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
        period = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
        if quota > 0:
            return max(1, round(quota / period))
    except (OSError, ValueError):
        pass
    return os.cpu_count() or 1


class ModelRunner:
    def __init__(self, model_path, max_new_tokens=96):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        torch.set_num_threads(cpu_limit())
        self.max_new_tokens = max_new_tokens
        self.tok = AutoTokenizer.from_pretrained(model_path)
        self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float32)
        self.model.eval()

    def generate(self, text):
        """Return the raw text the model produced after the prompt (greedy decoding)."""
        enc = self.tok(build_prompt(text), return_tensors="pt", add_special_tokens=False)
        with self._torch.inference_mode():
            out = self.model.generate(
                **enc,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tok.eos_token_id,
                eos_token_id=self.tok.eos_token_id,
            )
        new_tokens = out[0][enc["input_ids"].shape[1]:]
        return self.tok.decode(new_tokens, skip_special_tokens=True).strip()
