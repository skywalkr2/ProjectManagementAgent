"""Resolve stage references at config load, then against actual registries at startup.

An identifier that belongs to a plugin which is not running (not enabled, or failed to load) is tolerated: its stages
stay in config and show as unavailable at runtime. Only references that no running plugin or the core can explain are
errors, so disabling a plugin never stops the workspace from starting.
"""

from engine.config.loader import ConfigError
from engine.config.schema import STAGE_WORDING


def _dormant(identifier, running):
    return "/" in identifier and identifier.split("/")[0] not in running


def validate_stages(config, records, checks, tasks, running=None):
    """`running` is the set of plugin names whose contributions are in the registries; None means trust every id."""
    running = set(running) if running is not None else None
    for kind, settings in config.types.items():
        if running is not None and _dormant(kind, running):
            continue
        if kind not in records:
            raise ConfigError(f"stages.yaml: unknown record type {kind}")
        stages = settings.stages or []
        for stage in stages:
            for check in stage.entry:
                if check not in checks and not (running is not None and _dormant(check, running)):
                    raise ConfigError(f"stages.yaml: {kind}/{stage.id}: unknown entry check {check}")
            for task in stage.starts:
                if task not in tasks and not (running is not None and _dormant(task, running)):
                    raise ConfigError(f"stages.yaml: {kind}/{stage.id}: unknown task kind {task}")
        if (settings.moves or config.moves) == "rule":
            for stage in stages[1:]:
                if not stage.entry:
                    raise ConfigError(f"stages.yaml: {kind}/{stage.id}: {STAGE_WORDING['check_unavailable_rule']}")


def validate_declared(cfg, config_dir):
    from engine.plugin_manifest import declared_plugins
    from engine.records import REGISTRY
    from engine.tasks import TASKS

    records, tasks, checks = set(REGISTRY), set(TASKS), set()
    running = set()
    for manifest in declared_plugins(config_dir, cfg.workspace.plugins.enabled):
        running.add(manifest.name)
        records.update(manifest.provides.record_types)
        tasks.update(manifest.provides.ai_task_kinds)
        checks.update(manifest.provides.stage_checks)
    validate_rules(cfg.rules, checks, running)
    validate_stages(cfg.stages, records, checks | {r.id for r in cfg.rules.rules}, tasks, running)


def validate_rules(config, checks, running=None):
    for rule in config.rules:
        if rule.id in checks:
            raise ConfigError(f"rules.yaml: rule id collides with code check {rule.id}")
        if rule.check is not None and rule.check not in checks:
            if running is not None and _dormant(rule.check, running):
                continue
            raise ConfigError(f"rules.yaml: {rule.id}: unknown code check {rule.check}")
