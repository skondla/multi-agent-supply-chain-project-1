"""LLMOps: Versioned prompt registry with A/B testing support."""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class PromptVersion:
    """A specific version of a prompt template."""

    def __init__(
        self,
        name: str,
        version: str,
        template: str,
        variables: list[str],
        description: str = "",
        metadata: dict | None = None,
    ):
        self.name = name
        self.version = version
        self.template = template
        self.variables = variables
        self.description = description
        self.metadata = metadata or {}
        self.hash = hashlib.sha256(template.encode()).hexdigest()[:8]
        self.created_at = datetime.now(timezone.utc)

    def render(self, **kwargs) -> str:
        """Render the prompt template with provided variables."""
        missing = [v for v in self.variables if v not in kwargs]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        return self.template.format(**kwargs)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "hash": self.hash,
            "variables": self.variables,
            "description": self.description,
            "metadata": self.metadata,
        }


class ABTestConfig:
    """Configuration for A/B testing two prompt versions."""

    def __init__(
        self,
        variant_a: str,
        variant_b: str,
        traffic_split: float = 0.5,
        experiment_id: str | None = None,
    ):
        self.variant_a = variant_a
        self.variant_b = variant_b
        self.traffic_split = traffic_split
        self.experiment_id = experiment_id or f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.metrics: dict[str, dict] = {"a": {}, "b": {}}

    def select_variant(self) -> tuple[str, str]:
        """Select a variant based on traffic split. Returns (variant_label, version)."""
        if random.random() < self.traffic_split:
            return "a", self.variant_a
        return "b", self.variant_b

    def record_metric(self, variant: str, metric_name: str, value: float) -> None:
        """Record a metric for a variant."""
        if variant not in self.metrics:
            self.metrics[variant] = {}
        if metric_name not in self.metrics[variant]:
            self.metrics[variant][metric_name] = []
        self.metrics[variant][metric_name].append(value)


class PromptRegistry:
    """Central registry for all agent prompts with versioning and A/B testing."""

    def __init__(self):
        self._prompts: dict[str, dict[str, PromptVersion]] = {}
        self._ab_tests: dict[str, ABTestConfig] = {}
        self._usage_log: list[dict] = []
        self._load_from_files()

    def _load_from_files(self) -> None:
        """Load prompts from JSON files in the prompts directory."""
        if not PROMPTS_DIR.exists():
            logger.warning("prompts_dir_not_found", path=str(PROMPTS_DIR))
            return

        for prompt_file in PROMPTS_DIR.glob("*.json"):
            try:
                with prompt_file.open() as f:
                    data = json.load(f)
                    prompt_name = data["name"]
                    for version_data in data.get("versions", []):
                        self.register(
                            name=prompt_name,
                            version=version_data["version"],
                            template=version_data["template"],
                            variables=version_data.get("variables", []),
                            description=version_data.get("description", ""),
                            metadata=version_data.get("metadata", {}),
                        )
                logger.info("prompts_loaded", file=prompt_file.name)
            except Exception as e:
                logger.error("prompt_load_failed", file=prompt_file.name, error=str(e))

    def register(
        self,
        name: str,
        version: str,
        template: str,
        variables: list[str],
        description: str = "",
        metadata: dict | None = None,
    ) -> PromptVersion:
        """Register a new prompt version."""
        if name not in self._prompts:
            self._prompts[name] = {}

        prompt = PromptVersion(
            name=name,
            version=version,
            template=template,
            variables=variables,
            description=description,
            metadata=metadata,
        )
        self._prompts[name][version] = prompt
        logger.debug("prompt_registered", name=name, version=version)
        return prompt

    def get(self, name: str, version: str = "latest") -> PromptVersion:
        """Get a specific prompt version."""
        if name not in self._prompts:
            raise KeyError(f"Prompt '{name}' not found in registry")

        versions = self._prompts[name]
        if version == "latest":
            # Return the highest version (semantic versioning)
            version = sorted(versions.keys())[-1]

        if version not in versions:
            raise KeyError(f"Version '{version}' of prompt '{name}' not found")

        return versions[version]

    def render(
        self,
        name: str,
        version: str = "latest",
        agent_name: str = "unknown",
        **kwargs,
    ) -> tuple[str, dict]:
        """Render a prompt and log its usage. Returns (rendered_text, metadata)."""
        # Check for active A/B test
        ab_key = f"{name}:ab"
        if ab_key in self._ab_tests:
            ab_test = self._ab_tests[ab_key]
            variant_label, version = ab_test.select_variant()
        else:
            variant_label = "default"

        prompt = self.get(name, version)
        rendered = prompt.render(**kwargs)

        # Log usage
        usage = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_name": name,
            "version": version,
            "agent": agent_name,
            "variant": variant_label,
            "hash": prompt.hash,
            "variable_keys": list(kwargs.keys()),
        }
        self._usage_log.append(usage)
        if len(self._usage_log) > 10000:
            self._usage_log = self._usage_log[-5000:]

        logger.debug("prompt_rendered", **{k: v for k, v in usage.items() if k != "timestamp"})
        return rendered, usage

    def start_ab_test(
        self,
        prompt_name: str,
        variant_a_version: str,
        variant_b_version: str,
        traffic_split: float = 0.5,
    ) -> str:
        """Start an A/B test between two prompt versions."""
        ab_key = f"{prompt_name}:ab"
        self._ab_tests[ab_key] = ABTestConfig(
            variant_a=variant_a_version,
            variant_b=variant_b_version,
            traffic_split=traffic_split,
        )
        experiment_id = self._ab_tests[ab_key].experiment_id
        logger.info(
            "ab_test_started",
            prompt=prompt_name,
            variant_a=variant_a_version,
            variant_b=variant_b_version,
            experiment_id=experiment_id,
        )
        return experiment_id

    def stop_ab_test(self, prompt_name: str) -> dict | None:
        """Stop an A/B test and return results."""
        ab_key = f"{prompt_name}:ab"
        if ab_key not in self._ab_tests:
            return None

        test = self._ab_tests.pop(ab_key)
        logger.info("ab_test_stopped", prompt=prompt_name, experiment_id=test.experiment_id)
        return {
            "experiment_id": test.experiment_id,
            "variant_a": test.variant_a,
            "variant_b": test.variant_b,
            "metrics": test.metrics,
        }

    def list_prompts(self) -> list[dict]:
        """List all registered prompts and their versions."""
        result = []
        for name, versions in self._prompts.items():
            result.append({
                "name": name,
                "versions": [v.to_dict() for v in versions.values()],
                "latest_version": sorted(versions.keys())[-1],
                "ab_test_active": f"{name}:ab" in self._ab_tests,
            })
        return result

    def get_usage_stats(self) -> dict:
        """Get prompt usage statistics."""
        stats: dict[str, Any] = {}
        for usage in self._usage_log:
            key = f"{usage['prompt_name']}:{usage['version']}"
            stats[key] = stats.get(key, 0) + 1
        return stats


# Singleton registry instance
_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    """Get or create the singleton prompt registry."""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry
