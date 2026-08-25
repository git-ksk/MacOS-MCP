"""Tests for resolving running applications without an active run loop.

NSWorkspace only refreshes its application list from notifications delivered on
a run loop. This process never runs one, so anything reading that list has to
drain the queued sources first or it sees whatever was running at first read.
"""

import pytest
from unittest.mock import MagicMock

from macos_mcp.ax import core as ax_core
from macos_mcp.ax.controls import ApplicationControl


@pytest.mark.unit
class TestDrainRunLoop:
    def test_pumps_the_run_loop_without_blocking(self, mocker):
        """One non-blocking pass, which is all NSWorkspace needs to catch up."""
        run_in_mode = mocker.patch("macos_mcp.ax.core.CFRunLoopRunInMode")

        ax_core._DrainRunLoop()

        run_in_mode.assert_called_once()
        _mode, timeout, return_after_source = run_in_mode.call_args[0]
        assert timeout == 0  # must never block the caller
        assert return_after_source is True


@pytest.mark.unit
class TestGetRunningApplicationsRaw:
    def test_drains_before_reading_the_list(self, mocker):
        """The refresh has to happen before NSWorkspace is asked, not after."""
        calls = []
        mocker.patch(
            "macos_mcp.ax.core._DrainRunLoop",
            side_effect=lambda: calls.append("drain"),
        )
        workspace = MagicMock()
        workspace.runningApplications.side_effect = lambda: calls.append("read") or []
        nsworkspace = MagicMock()
        nsworkspace.sharedWorkspace.return_value = workspace
        mocker.patch("macos_mcp.ax.core.NSWorkspace", nsworkspace)

        ax_core.GetRunningApplicationsRaw()

        assert calls == ["drain", "read"]


@pytest.mark.unit
class TestApplicationControlBundleIdentifier:
    def test_resolves_from_pid_not_the_workspace_list(self, mocker):
        """A process missing from the stale list still resolves by PID."""
        mocker.patch("macos_mcp.ax.controls.GetElementPid", return_value=4321)
        running_app = MagicMock()
        running_app.bundleIdentifier.return_value = "com.example.launched"
        ns_running_application = MagicMock()
        ns_running_application.runningApplicationWithProcessIdentifier_.return_value = (
            running_app
        )
        mocker.patch("Cocoa.NSRunningApplication", ns_running_application)
        workspace = MagicMock()
        workspace.runningApplications.return_value = []  # stale: app not listed
        nsworkspace = MagicMock()
        nsworkspace.sharedWorkspace.return_value = workspace
        mocker.patch("macos_mcp.ax.core.NSWorkspace", nsworkspace)

        control = ApplicationControl(pid=4321)

        assert control.BundleIdentifier == "com.example.launched"
        ns_running_application.runningApplicationWithProcessIdentifier_.assert_called_once_with(
            4321
        )
        workspace.runningApplications.assert_not_called()
