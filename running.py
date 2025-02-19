import os
import json
import shutil
import requests
import zipfile
from typing import Optional, Dict
from pathlib import Path
from time import sleep
from datetime import datetime
from rich import print as rprint
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeRemainingColumn,
)
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.status import Status
from dotenv import load_dotenv

load_dotenv()

console = Console()


class LegacyConverter:
    def __init__(self, api_base_url: str = os.getenv("API_MOXIE_URL")):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.timeout = 600  # 10 minutes timeout
        self.console = Console()

    def _log_request_start(self, endpoint: str):
        """Log the start of an API request with rich formatting"""
        self.console.log(
            f"[bold blue]→[/bold blue] Starting request to [cyan]{endpoint}[/cyan]"
        )

    def _log_request_success(self, endpoint: str, duration: float):
        """Log successful API request with rich formatting"""
        self.console.log(
            f"[bold green]✓[/bold green] Request to [cyan]{endpoint}[/cyan] completed in [yellow]{duration:.2f}s[/yellow]"
        )

    def _log_request_error(self, endpoint: str, error: str):
        """Log API request error with rich formatting"""
        self.console.log(
            f"[bold red]✗[/bold red] Error in [cyan]{endpoint}[/cyan]: [red]{error}[/red]"
        )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make HTTP request with rich logging and proper error handling"""
        url = f"{self.api_base_url}/{endpoint}"
        kwargs.setdefault("timeout", self.timeout)

        self._log_request_start(endpoint)
        start_time = datetime.now()

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            duration = (datetime.now() - start_time).total_seconds()
            self._log_request_success(endpoint, duration)
            return response.json()
        except requests.RequestException as e:
            self._log_request_error(endpoint, str(e))
            raise

    def import_legacy(self, file_path: str) -> Dict:
        """Import legacy project with progress indication"""
        with self.console.status("[bold yellow]Uploading legacy project...") as status:
            with open(file_path, "rb") as f:
                files = {
                    "file": (
                        os.path.basename(file_path),
                        f,
                        "application/x-zip-compressed",  # Importante especificar o tipo correto
                    )
                }
                # Importante: Não devemos incluir o Content-Type no header para multipart/form-data
                headers = self.session.headers.copy()
                headers.pop("Content-Type", None)

                url = f"{self.api_base_url}/import-legacy"
                response = requests.post(
                    url, files=files, timeout=self.timeout, headers=headers
                )
                response.raise_for_status()
                status.update("[bold green]Legacy project uploaded successfully!")
                return response.json()

    def analyze_project(self, project_id: str) -> Dict:
        """Run project analysis with progress updates"""
        with self.console.status("[bold yellow]Analyzing project...") as status:
            response = self._make_request(
                "POST", "analysis", json={"project_id": project_id}
            )
            status.update("[bold green]Project analysis completed!")
            return response

    def generate_documentation(self, project_id: str) -> Dict:
        """Generate project documentation with progress updates"""
        with self.console.status("[bold yellow]Generating documentation...") as status:
            response = self._make_request(
                "POST",
                "documentation",
                json={"project_id": project_id, "api_key": os.getenv("API_KEY")},
            )
            status.update("[bold green]Documentation generated successfully!")
            return response

    def get_scaffolding(
        self, project_id: str, language: str, project_type: str, framework: str = ""
    ) -> Dict:
        """Get project scaffolding with status updates"""
        payload = {
            "project_id": project_id,
            "api_key": os.getenv("API_KEY"),
            "language": language,
            "project_type": project_type,
            "framework": framework,
        }
        with self.console.status(
            "[bold yellow]Fetching scaffolding configuration..."
        ) as status:
            response = self._make_request("POST", "scaffolding", json=payload)
            status.update("[bold green]Scaffolding configuration received!")
            return response

    def download_and_parse_scaffolding(self, scaffolding_url: str) -> list:
        """Download and parse scaffolding JSON with progress indication"""
        with self.console.status(
            "[bold yellow]Downloading scaffolding template..."
        ) as status:
            response = requests.get(scaffolding_url, timeout=self.timeout)
            response.raise_for_status()
            # Parse a string JSON para objeto Python
            try:
                if isinstance(response.text, str):
                    data = json.loads(response.text)
                else:
                    data = response.json()

                status.update("[bold green]Scaffolding template downloaded and parsed!")
                # Log para debug
                self.console.log(f"[dim]Received {len(data)} scaffolding items[/dim]")
                return data
            except json.JSONDecodeError as e:
                status.update("[bold red]Error parsing scaffolding JSON!")
                self.console.log(
                    "[red]Response content:[/red]", response.text[:200] + "..."
                )
                raise

    def create_scaffolding_structure(
        self, scaffolding_data: list, output_dir: str = "scaffolding"
    ):
        """Create scaffolding directory structure with visual tree representation"""
        # Remove existing scaffolding directory if it exists
        if os.path.exists(output_dir):
            with self.console.status(
                "[yellow]Removing existing scaffolding..."
            ) as status:
                shutil.rmtree(output_dir)
                status.update("[green]Existing scaffolding removed")

        # Create base directory
        os.makedirs(output_dir)

        # Create tree visualization
        tree = Tree(
            f"[bold blue]:file_folder: {output_dir}",
            guide_style="bold bright_blue",
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Creating project structure...", total=len(scaffolding_data)
            )

            for item in scaffolding_data:
                full_path = os.path.join(output_dir, item["full_path"])
                relative_path = item["full_path"]

                # Create parent directories if they don't exist
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                # Add to tree visualization
                if item["type"] == "directory":
                    os.makedirs(full_path, exist_ok=True)
                    tree.add(f"[bold blue]:file_folder: {relative_path}")
                else:  # file
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(f"# Purpose: {item['description']}\n")
                        f.write(
                            f"# Expected content type: {item['expected_content']}\n"
                        )
                    tree.add(f"[bold green]:page_facing_up: {relative_path}")

                progress.advance(task)

        # Display the final tree structure
        self.console.print("\n[bold cyan]Created Project Structure:[/bold cyan]")
        self.console.print(tree)


def print_config_summary(config: dict):
    """Print a summary of the configuration"""
    table = Table(
        title="Configuration Summary", show_header=True, header_style="bold magenta"
    )
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    for key, value in config.items():
        table.add_row(key, str(value))

    console.print(table)


def main(
    legacy_file_path: Optional[str] = None,
    project_id: Optional[str] = None,
    language: str = os.getenv("LANGUAGE", "csharp"),
    project_type: str = os.getenv("PROJECT_TYPE", "batch"),
    framework: str = os.getenv("FRAMEWORK", "dotnet"),
):

    console.clear()
    console.print(
        Panel.fit(
            "[bold blue]Legacy Project Converter[/bold blue]\n"
            "[cyan]Converting legacy projects to modern architectures[/cyan]",
            border_style="blue",
        )
    )

    # Print configuration summary
    config = {
        "Project ID": project_id or "New Project",
        "Legacy File": legacy_file_path or "N/A",
        "Language": language,
        "Project Type": project_type,
        "Framework": framework,
    }
    print_config_summary(config)

    converter = LegacyConverter()

    try:
        if project_id:
            console.print("\n[bold blue]Using Existing Project[/bold blue]")
            try:
                with console.status(
                    "[bold yellow]Checking for existing scaffolding..."
                ):
                    scaffolding = converter.get_scaffolding(
                        project_id, language, project_type, framework
                    )
                    final_scaffolding_url = scaffolding["scaffolding"]["final"]

                console.print("[bold green]✓[/bold green] Found existing scaffolding!")
                scaffolding_data = converter.download_and_parse_scaffolding(
                    final_scaffolding_url
                )

                # Debug logs
                console.print(
                    "[dim]Scaffolding data type:[/dim]", type(scaffolding_data)
                )
                console.print(
                    "[dim]Scaffolding data preview:[/dim]", str(scaffolding_data)[:200]
                )

                # Ajuste no tratamento do JSON
                try:
                    if isinstance(scaffolding_data, str):
                        scaffolding_data = json.loads(scaffolding_data)

                    # Se o resultado ainda não for uma lista, pode estar dentro de alguma chave
                    if not isinstance(scaffolding_data, list):
                        # Tenta extrair a lista de dentro do objeto, se existir
                        for key, value in scaffolding_data.items():
                            if isinstance(value, list):
                                scaffolding_data = value
                                break

                    if not isinstance(scaffolding_data, list):
                        raise ValueError(
                            f"Unable to extract list from scaffolding data. Got type: {type(scaffolding_data)}"
                        )

                    console.print(
                        f"[green]Successfully parsed scaffolding data. Found {len(scaffolding_data)} items.[/green]"
                    )

                except Exception as e:
                    console.print("[red]Error parsing scaffolding data:[/red]", str(e))
                    console.print(
                        "[yellow]Raw scaffolding data:[/yellow]", scaffolding_data
                    )
                    raise

                converter.create_scaffolding_structure(scaffolding_data)
                console.print(
                    "[bold green]✓[/bold green] Project structure created successfully!"
                )
                return
            except requests.RequestException:
                console.print(
                    "[yellow]!![/yellow] No existing scaffolding found, continuing with analysis..."
                )

                with console.status(
                    "[bold yellow]Processing existing project..."
                ) as status:
                    status.update("Running analysis...")
                    converter.analyze_project(project_id)

                    status.update("Generating documentation...")
                    converter.generate_documentation(project_id)

                    status.update("Creating scaffolding...")
                    scaffolding = converter.get_scaffolding(
                        project_id, language, project_type, framework
                    )
                    final_scaffolding_url = scaffolding["scaffolding"]["final"]

                    scaffolding_data = converter.download_and_parse_scaffolding(
                        final_scaffolding_url
                    )
                    if not isinstance(scaffolding_data, list):
                        console.print(
                            "[yellow]Warning:[/yellow] Converting scaffolding data format"
                        )
                        scaffolding_data = (
                            json.loads(scaffolding_data)
                            if isinstance(scaffolding_data, str)
                            else scaffolding_data
                        )
                    converter.create_scaffolding_structure(scaffolding_data)

                console.print(
                    "[bold green]✓[/bold green] Project processing completed!"
                )
                return

        if not legacy_file_path:
            console.print(
                "[bold red]Error:[/bold red] Legacy file path is required for new projects"
            )
            return

        console.print("\n[bold blue]Starting New Project Process[/bold blue]")

        # Import legacy project
        import_result = converter.import_legacy(legacy_file_path)
        project_id = import_result["project_id"]
        console.print(
            f"[bold green]✓[/bold green] Project imported with ID: [cyan]{project_id}[/cyan]"
        )

        # Process project
        with console.status("[bold yellow]Processing project...") as status:
            status.update("Running analysis...")
            converter.analyze_project(project_id)

            status.update("Generating documentation...")
            converter.generate_documentation(project_id)

            status.update("Creating scaffolding...")
            scaffolding = converter.get_scaffolding(
                project_id, language, project_type, framework
            )
            final_scaffolding_url = scaffolding["scaffolding"]["final"]

            scaffolding_data = converter.download_and_parse_scaffolding(
                final_scaffolding_url
            )
            if not isinstance(scaffolding_data, list):
                console.print(
                    "[yellow]Warning:[/yellow] Converting scaffolding data format"
                )
                scaffolding_data = (
                    json.loads(scaffolding_data)
                    if isinstance(scaffolding_data, str)
                    else scaffolding_data
                )
            converter.create_scaffolding_structure(scaffolding_data)

        # Final success message
        console.print(
            Panel.fit(
                f"[bold green]Project Successfully Converted![/bold green]\n"
                f"[cyan]Project ID: {project_id}[/cyan]\n"
                "[yellow]Save this ID for future use[/yellow]",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(
            Panel.fit(
                f"[bold red]Error During Conversion[/bold red]\n"
                f"[red]{str(e)}[/red]",
                border_style="red",
            )
        )
        raise


if __name__ == "__main__":

    # Configurações do projeto

    # Descomente a linha abaixo e insira um project_id existente para reutilizar um projeto

    # project_id = "1576cede-c694-48ac-aea1-04e4177dcdb9"
    project_id = None

    # Configurações para novo projeto (usado apenas se project_id for None)
    legacy_file_path = "LT2000B.zip"  # Substitua pelo caminho do seu arquivo ZIP

    # Verifica se o arquivo existe antes de prosseguir
    if not project_id and not os.path.exists(legacy_file_path):
        console.print(
            f"[bold red]Error:[/bold red] File {legacy_file_path} not found in current directory"
        )
        console.print(
            f"[yellow]Current directory:[/yellow] {os.path.abspath(os.path.dirname(__file__))}"
        )
        exit(1)

    # your final stack config (output)
    config = {
        "language": os.getenv("LANGUAGE", "csharp"),
        "project_type": os.getenv("PROJECT_TYPE", "batch"),
        "framework": os.getenv("FRAMEWORK", "dotnet"),
    }

    try:
        if project_id:
            console.print("[bold blue]Using existing project ID...[/bold blue]")
            main(project_id=project_id, **config)
        else:
            console.print("[bold blue]Starting new project process...[/bold blue]")
            main(legacy_file_path=legacy_file_path, **config)
    except KeyboardInterrupt:
        console.print("\n[bold red]Process interrupted by user[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
    finally:
        console.print("\n[bold blue]Process finished[/bold blue]")
