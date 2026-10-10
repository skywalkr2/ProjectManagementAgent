"""Resolve stage references at config load, then against actual registries at startup."""

from engine.config.loader import ConfigError


def validate_stages(config, records, checks, tasks):
    for kind, settings in config.types.items():
        if kind not in records:
            raise ConfigError(f"stages.yaml: unknown record type {kind}")
        for stage in settings.stages:
            for check in stage.entry:
                if check not in checks:
                    raise ConfigError(f"stages.yaml: {kind}/{stage.id}: unknown entry check {check}")
            for task in stage.starts:
                if task not in tasks:
                    raise ConfigError(f"stages.yaml: {kind}/{stage.id}: unknown task kind {task}")


def validate_declared(cfg, config_dir):
    from engine.plugin_manifest import declared_plugins
    from engine.records import REGISTRY
    from engine.tasks import TASKS

    records, tasks, checks = set(REGISTRY), set(TASKS), set()
    for manifest in declared_plugins(config_dir, cfg.workspace.plugins.enabled):
        records.update(manifest.provides.record_types)
        tasks.update(manifest.provides.ai_task_kinds)
        checks.update(manifest.provides.stage_checks)
    validate_stages(cfg.stages, records, checks, tasks)
