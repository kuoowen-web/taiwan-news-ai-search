"""
Console Tracer for Reasoning Module

Provides real-time colored console output for debugging and monitoring
the reasoning orchestrator's execution flow.

Design Principles:
- Content-aware: Display full objects/strings based on verbosity level
- Visual clarity: Use rich library for panels, syntax highlighting, and colors
- Context managers: Clean 'with' syntax for agent execution spans
- Zero coupling: Can be completely disabled via config without code changes
"""

import time
import traceback
from typing import Any, Dict, List, Optional, Union
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.pretty import Pretty
    from rich.text import Text
    from rich.tree import Tree
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class ConsoleTracer:
    """Real-time console tracer with full content visibility."""

    VERBOSITY_LEVELS = {
        "ERROR": 0,
        "WARN": 1,
        "INFO": 2,
        "DEBUG": 3,
        "TRACE": 4
    }

    def __init__(self, query_id: str, verbosity: str = "DEBUG", enable_colors: bool = True):
        """
        Initialize console tracer.

        Args:
            query_id: Unique identifier for the research session
            verbosity: One of ERROR, WARN, INFO, DEBUG, TRACE (default: DEBUG)
            enable_colors: Whether to use colored output (default: True)
        """
        self.query_id = query_id
        self.verbosity_level = self.VERBOSITY_LEVELS.get(verbosity.upper(), 3)
        self.enable_colors = enable_colors and RICH_AVAILABLE

        if self.enable_colors:
            self.console = Console(force_terminal=True, color_system="auto")
        else:
            self.console = None

        self.start_time = time.time()
        self.iteration_start_time = None
        self.current_iteration = 0

        # Span stack for nested context managers
        self._span_stack: List['AgentSpan'] = []

    def _should_log(self, level: str) -> bool:
        """Check if message should be logged based on verbosity level."""
        return self.VERBOSITY_LEVELS.get(level.upper(), 0) <= self.verbosity_level

    def _format_content_preview(self, content: Any, max_length: Optional[int] = None) -> str:
        """
        Format content preview based on verbosity level.

        Args:
            content: Any content to format (string, dict, list, object)
            max_length: Override default length limit

        Returns:
            Formatted string preview
        """
        if content is None:
            return "None"

        # Determine max length based on verbosity if not specified
        if max_length is None:
            if self.verbosity_level >= 4:  # TRACE
                max_length = None  # No limit
            elif self.verbosity_level >= 3:  # DEBUG
                max_length = 2000
            elif self.verbosity_level >= 2:  # INFO
                max_length = 500
            else:  # WARN, ERROR
                max_length = 100

        # Convert to string
        if isinstance(content, str):
            text = content
        elif isinstance(content, (dict, list)):
            import json
            text = json.dumps(content, indent=2, ensure_ascii=False, default=str)
        else:
            text = str(content)

        # Truncate if needed
        if max_length and len(text) > max_length:
            return f"{text[:max_length]}... ({len(text)} chars total)"

        return text

    def _display_panel(self, title: str, content: Any, border_style: str = "blue",
                       title_style: str = "bold white"):
        """
        Display content in a rich panel.

        Args:
            title: Panel title
            content: Content to display
            border_style: Rich color for border
            title_style: Rich style for title
        """
        if not self.enable_colors:
            print(f"\n[{title}]")
            print(self._format_content_preview(content))
            return

        # Format content based on type
        if isinstance(content, str):
            # Try to detect markdown/code content
            if content.strip().startswith(('```', '#', '-', '*', '|')):
                renderable = Syntax(content, "markdown", theme="monokai", word_wrap=True)
            else:
                renderable = content
        elif isinstance(content, dict):
            renderable = Pretty(content, expand_all=True)
        elif isinstance(content, list):
            renderable = Pretty(content, expand_all=True)
        else:
            renderable = str(content)

        panel = Panel(
            renderable,
            title=f"[{title_style}]{title}[/{title_style}]",
            border_style=border_style,
            expand=False
        )
        self.console.print(panel)

    def _print(self, message: str, style: str = ""):
        """Print message with optional styling."""
        if self.enable_colors:
            self.console.print(message, style=style)
        else:
            print(message)

    # ============================================================================
    # Main Tracing Methods
    # ============================================================================

    def start_research(self, query: str, mode: str, items: List[Any]):
        """
        Log research session start.

        Args:
            query: User query
            mode: Research mode (strict, balanced, exploratory)
            items: Full list of retrieved items
        """
        if not self._should_log("INFO"):
            return

        self.start_time = time.time()

        if self.enable_colors:
            header = Panel(
                f"[bold cyan]🔍 DEEP RESEARCH STARTED[/bold cyan]\n"
                f"Query: {query}\n"
                f"Mode: [yellow]{mode}[/yellow] | Sources: [green]{len(items)}[/green]",
                border_style="cyan",
                expand=False
            )
            self.console.print("\n")
            self.console.print(header)
        else:
            print("\n" + "="*70)
            print(f"🔍 DEEP RESEARCH STARTED")
            print(f"Query: {query}")
            print(f"Mode: {mode} | Sources: {len(items)}")
            print("="*70)

        # Show preview of sources at DEBUG level
        if self._should_log("DEBUG") and items:
            preview_count = min(3, len(items))
            preview_text = "\nFirst {} sources preview:\n".format(preview_count)
            for i, item in enumerate(items[:preview_count], 1):
                title = getattr(item, 'title', 'N/A')
                url = getattr(item, 'url', 'N/A')
                preview_text += f"  [{i}] {title}\n      {url}\n"
            self._print(preview_text, style="dim")

    def source_filtering(self, original_items: List[Any], filtered_items: List[Any], mode: str):
        """
        Log source filtering operation.

        Args:
            original_items: Full list before filtering
            filtered_items: Filtered list after tier/quality filtering
            mode: Research mode
        """
        if not self._should_log("INFO"):
            return

        original_count = len(original_items)
        filtered_count = len(filtered_items)

        if self.enable_colors:
            self.console.print(
                f"\n  🔽 [yellow]Filtering:[/yellow] {original_count} → {filtered_count} sources "
                f"[dim](mode: {mode})[/dim]"
            )
        else:
            print(f"\n  🔽 Filtering: {original_count} → {filtered_count} sources (mode: {mode})")

    def context_formatted(self, source_map: Dict[int, Any], formatted_context: str):
        """
        Log formatted context creation.

        Args:
            source_map: Dictionary mapping citation numbers to sources
            formatted_context: The formatted context string
        """
        if not self._should_log("DEBUG"):
            return

        context_length = len(formatted_context)
        source_count = len(source_map)

        self._print(
            f"\n  📋 Context: {source_count} sources, {context_length:,} chars",
            style="dim cyan"
        )

        # Show formatted context preview at TRACE level
        if self._should_log("TRACE"):
            preview = self._format_content_preview(formatted_context, max_length=2000)
            self._display_panel(
                "Formatted Context Preview",
                preview,
                border_style="cyan",
                title_style="dim cyan"
            )

    def start_iteration(self, iteration: int, max_iterations: int):
        """
        Log iteration start.

        Args:
            iteration: Current iteration number (1-indexed)
            max_iterations: Maximum allowed iterations
        """
        if not self._should_log("INFO"):
            return

        self.current_iteration = iteration
        self.iteration_start_time = time.time()

        if self.enable_colors:
            self.console.print(
                f"\n[bold]┌─ ITERATION {iteration}/{max_iterations} "
                + "─" * 50 + "┐[/bold]"
            )
        else:
            print(f"\n┌─ ITERATION {iteration}/{max_iterations} " + "─" * 50 + "┐")

    def end_iteration(self):
        """Log iteration end."""
        if not self._should_log("INFO"):
            return

        if self.iteration_start_time:
            duration = time.time() - self.iteration_start_time
            if self.enable_colors:
                self.console.print(
                    f"[dim]└─ Iteration complete ({duration:.1f}s) ─" + "─" * 43 + "┘[/dim]"
                )
            else:
                print(f"└─ Iteration complete ({duration:.1f}s) ─" + "─" * 43 + "┘")

    @contextmanager
    def agent_span(self, agent_name: str, method: str, input_data: Any):
        """
        Context manager for agent execution with automatic timing.

        Usage:
            with tracer.agent_span("analyst", "research", input_dict) as span:
                result = await agent.research(...)
                span.set_result(result)

        Args:
            agent_name: Name of agent (analyst, critic, writer)
            method: Method being called (research, revise, review, compose)
            input_data: Input parameters (will be displayed based on verbosity)

        Yields:
            AgentSpan: Span object to set result
        """
        span = AgentSpan(self, agent_name, method, input_data)
        self._span_stack.append(span)

        try:
            span.start()
            yield span
        except Exception as e:
            span.set_error(e)
            raise
        finally:
            span.end()
            if self._span_stack and self._span_stack[-1] == span:
                self._span_stack.pop()

    def condition_branch(self, condition_type: str, choice: str, details: Dict[str, Any]):
        """
        Log a conditional branch in the execution flow.

        Args:
            condition_type: Type of condition (GAP_DETECTION, CONVERGENCE, HALLUCINATION_GUARD)
            choice: The decision/choice made
            details: Additional details about the decision
        """
        if not self._should_log("DEBUG"):
            return

        if self.enable_colors:
            self.console.print(
                f"\n  🔀 [bold magenta]{condition_type}[/bold magenta]: {choice}",
                style="magenta"
            )
        else:
            print(f"\n  🔀 {condition_type}: {choice}")

        # Show details at TRACE level
        if self._should_log("TRACE") and details:
            self._display_panel(
                f"{condition_type} Details",
                details,
                border_style="magenta",
                title_style="dim magenta"
            )

    def context_update(self, action: str, details: Dict[str, Any]):
        """
        Log context updates (e.g., secondary search results added).

        Args:
            action: Type of update (SECONDARY_SEARCH, etc.)
            details: Update details
        """
        if not self._should_log("DEBUG"):
            return

        if self.enable_colors:
            self.console.print(
                f"  📝 [cyan]{action}[/cyan]: {details}",
                style="dim"
            )
        else:
            print(f"  📝 {action}: {details}")

    def end_research(self, final_status: str, iterations: int, total_time: float):
        """
        Log research session end.

        Args:
            final_status: Final status (PASS, WARN, MAX_ITERATIONS)
            iterations: Total iterations executed
            total_time: Total execution time in seconds
        """
        if not self._should_log("INFO"):
            return

        if self.enable_colors:
            status_color = "green" if final_status == "PASS" else "yellow"
            footer = Panel(
                f"[bold {status_color}]✅ RESEARCH COMPLETE[/bold {status_color}]\n"
                f"Status: [{status_color}]{final_status}[/{status_color}] | "
                f"Iterations: [cyan]{iterations}[/cyan] | "
                f"Time: [cyan]{total_time:.1f}s[/cyan]",
                border_style=status_color,
                expand=False
            )
            self.console.print("\n")
            self.console.print(footer)
            self.console.print("\n")
        else:
            print("\n" + "="*70)
            print(f"✅ RESEARCH COMPLETE")
            print(f"Status: {final_status} | Iterations: {iterations} | Time: {total_time:.1f}s")
            print("="*70 + "\n")

    def error(self, message: str, exception: Optional[Exception] = None):
        """
        Log an error.

        Args:
            message: Error message
            exception: Optional exception object
        """
        if not self._should_log("ERROR"):
            return

        if self.enable_colors:
            self.console.print(f"\n[bold red]❌ ERROR:[/bold red] {message}", style="red")
        else:
            print(f"\n❌ ERROR: {message}")

        if exception and self._should_log("DEBUG"):
            if self.enable_colors:
                self.console.print("[dim red]" + traceback.format_exc() + "[/dim red]")
            else:
                print(traceback.format_exc())


class AgentSpan:
    """
    Context manager for agent execution span.

    Automatically tracks timing and displays input/output.
    """

    def __init__(self, tracer: ConsoleTracer, agent_name: str, method: str, input_data: Any):
        self.tracer = tracer
        self.agent_name = agent_name
        self.method = method
        self.input_data = input_data
        self.result = None
        self.error_obj = None
        self.start_time = None
        self.end_time = None

    def start(self):
        """Display agent start."""
        self.start_time = time.time()

        if not self.tracer._should_log("INFO"):
            return

        # Agent header
        emoji_map = {
            "analyst": "📊",
            "critic": "🎭",
            "writer": "✍️",
            "clarification": "❓"
        }
        emoji = emoji_map.get(self.agent_name, "🤖")

        if self.tracer.enable_colors:
            self.tracer.console.print(
                f"\n│ [bold blue]{emoji} {self.agent_name.title()}[/bold blue] → "
                f"[cyan]{self.method}()[/cyan]"
            )
        else:
            print(f"\n│ {emoji} {self.agent_name.title()} → {self.method}()")

        # Show input at DEBUG level
        if self.tracer._should_log("DEBUG") and self.input_data:
            self.tracer._display_panel(
                f"{self.agent_name.title()} Input",
                self.input_data,
                border_style="blue",
                title_style="dim blue"
            )

    def set_result(self, result: Any):
        """Set the agent execution result."""
        self.result = result

    def set_error(self, error: Exception):
        """Set error if execution failed."""
        self.error_obj = error

    def end(self):
        """Display agent end."""
        self.end_time = time.time()

        if not self.tracer._should_log("INFO"):
            return

        duration = self.end_time - self.start_time if self.start_time else 0

        if self.error_obj:
            # Error case
            if self.tracer.enable_colors:
                self.tracer.console.print(
                    f"│   [red]❌ Failed ({duration:.1f}s)[/red]: {str(self.error_obj)}"
                )
            else:
                print(f"│   ❌ Failed ({duration:.1f}s): {str(self.error_obj)}")
        else:
            # Success case
            if self.tracer.enable_colors:
                self.tracer.console.print(
                    f"│   [green]✅ Complete ({duration:.1f}s)[/green]"
                )
            else:
                print(f"│   ✅ Complete ({duration:.1f}s)")

            # Show output at DEBUG level
            if self.tracer._should_log("DEBUG") and self.result is not None:
                self.tracer._display_panel(
                    f"{self.agent_name.title()} Output",
                    self.result,
                    border_style="green",
                    title_style="dim green"
                )
