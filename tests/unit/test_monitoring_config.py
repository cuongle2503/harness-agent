"""Unit tests for monitoring config dataclasses."""

from __future__ import annotations

from logging import DEBUG, INFO, WARNING

from harness_agent.monitoring.config import (
    AlertChannelConfig,
    AlertConfig,
    LoggingConfig,
    StreamingConfig,
)


class TestStreamingConfig:
    """Tests for StreamingConfig."""

    def test_default_modes_include_all_required(self) -> None:
        config = StreamingConfig()
        assert "messages" in config.modes
        assert "updates" in config.modes
        assert "custom" in config.modes
        assert "tasks" in config.modes

    def test_custom_modes_override_defaults(self) -> None:
        config = StreamingConfig(modes=["messages", "debug"])
        assert config.modes == ["messages", "debug"]
        assert "updates" not in config.modes

    def test_subgraphs_enabled_by_default(self) -> None:
        config = StreamingConfig()
        assert config.subgraphs is True

    def test_version_defaults_to_v2(self) -> None:
        config = StreamingConfig()
        assert config.version == "v2"

    def test_route_to_monitoring_enabled_by_default(self) -> None:
        config = StreamingConfig()
        assert config.route_to_monitoring is True

    def test_to_stream_kwargs_returns_correct_dict(self) -> None:
        config = StreamingConfig()
        kwargs = config.to_stream_kwargs()
        assert kwargs == {
            "stream_mode": ["messages", "updates", "custom", "tasks"],
            "subgraphs": True,
            "version": "v2",
        }


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_default_log_level_is_info(self) -> None:
        config = LoggingConfig()
        assert config.log_level == INFO

    def test_json_format_by_default(self) -> None:
        config = LoggingConfig()
        assert config.log_format == "json"

    def test_sensitive_data_excluded_by_default(self) -> None:
        config = LoggingConfig()
        assert config.exclude_sensitive is True

    def test_correlation_id_field_is_thread_id(self) -> None:
        config = LoggingConfig()
        assert config.correlation_id_field == "thread_id"

    def test_rotation_size_default_10mb(self) -> None:
        config = LoggingConfig()
        assert config.rotation_size_mb == 10

    def test_backup_count_default_5(self) -> None:
        config = LoggingConfig()
        assert config.backup_count == 5

    def test_console_enabled_by_default(self) -> None:
        config = LoggingConfig()
        assert config.enable_console is True

    def test_level_name_returns_human_readable(self) -> None:
        assert LoggingConfig(log_level=DEBUG).level_name() == "DEBUG"
        assert LoggingConfig(log_level=INFO).level_name() == "INFO"
        assert LoggingConfig(log_level=WARNING).level_name() == "WARNING"

    def test_log_file_can_be_none(self) -> None:
        config = LoggingConfig(log_file=None)
        assert config.log_file is None


class TestAlertChannelConfig:
    """Tests for AlertChannelConfig."""

    def test_disabled_by_default(self) -> None:
        channel = AlertChannelConfig(channel_type="slack")
        assert channel.enabled is False

    def test_endpoint_empty_by_default(self) -> None:
        channel = AlertChannelConfig(channel_type="email")
        assert channel.endpoint == ""

    def test_min_severity_defaults_to_high(self) -> None:
        channel = AlertChannelConfig(channel_type="webhook")
        assert channel.min_severity == "HIGH"

    def test_can_configure_all_fields(self) -> None:
        channel = AlertChannelConfig(
            channel_type="slack",
            enabled=True,
            endpoint="https://hooks.slack.com/xyz",
            min_severity="MEDIUM",
        )
        assert channel.channel_type == "slack"
        assert channel.enabled is True
        assert channel.endpoint == "https://hooks.slack.com/xyz"
        assert channel.min_severity == "MEDIUM"


class TestAlertConfig:
    """Tests for AlertConfig."""

    def test_enabled_by_default(self) -> None:
        config = AlertConfig()
        assert config.enabled is True

    def test_default_cooldown_300_seconds(self) -> None:
        config = AlertConfig()
        assert config.cooldown_seconds == 300.0

    def test_default_rule_check_interval_30_seconds(self) -> None:
        config = AlertConfig()
        assert config.rule_check_interval_seconds == 30.0

    def test_channels_empty_by_default(self) -> None:
        config = AlertConfig()
        assert config.channels == []

    def test_can_add_channels(self) -> None:
        channel = AlertChannelConfig(channel_type="slack", enabled=True)
        config = AlertConfig(channels=[channel])
        assert len(config.channels) == 1
        assert config.channels[0].channel_type == "slack"
