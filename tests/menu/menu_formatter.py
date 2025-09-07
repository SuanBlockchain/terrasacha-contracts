"""
Professional menu formatting utilities for Cardano dApp CLI interface.
Provides consistent styling, colors, and layout for interactive menus.
"""


# ANSI color codes for professional menu styling
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class MenuFormatter:
    """Professional menu formatting class with consistent styling"""

    def __init__(self, width: int = 80):
        self.width = width

    def print_header(self, title: str, subtitle: str = None):
        """Print a professional header with branding"""
        print("\n" + Colors.HEADER + "╔" + "═" * (self.width - 2) + "╗" + Colors.ENDC)
        print(
            Colors.HEADER
            + "║"
            + Colors.BOLD
            + f"{title:^{self.width-2}}"
            + Colors.ENDC
            + Colors.HEADER
            + "║"
            + Colors.ENDC
        )
        if subtitle:
            print(
                Colors.HEADER
                + "║"
                + Colors.OKBLUE
                + f"{subtitle:^{self.width-2}}"
                + Colors.ENDC
                + Colors.HEADER
                + "║"
                + Colors.ENDC
            )
        print(Colors.HEADER + "╚" + "═" * (self.width - 2) + "╝" + Colors.ENDC)

    def print_status_bar(
        self, network: str, balance: float, contracts_status: str = None, wallet_name: str = None
    ):
        """Print a status information bar"""
        status_line = f"Network: {network}"
        if wallet_name:
            status_line += f" | Wallet: {wallet_name}"
        status_line += f" | Balance: {balance:.6f} ADA"
        if contracts_status:
            status_line += f" | Contracts: {contracts_status}"

        print(
            f"{Colors.OKBLUE}┌{Colors.ENDC}"
            + "─" * (self.width - 2)
            + f"{Colors.OKBLUE}┐{Colors.ENDC}"
        )
        print(
            f"{Colors.OKBLUE}│{Colors.ENDC} {status_line:<{self.width-4}} {Colors.OKBLUE}│{Colors.ENDC}"
        )
        print(
            f"{Colors.OKBLUE}└{Colors.ENDC}"
            + "─" * (self.width - 2)
            + f"{Colors.OKBLUE}┘{Colors.ENDC}"
        )

    def print_section(self, title: str):
        """Print a section separator"""
        print(
            f"\n{Colors.OKBLUE}┌─ {Colors.BOLD}{title}{Colors.ENDC} {Colors.OKBLUE}{'─' * (self.width - len(title) - 4)}{Colors.ENDC}"
        )

    def print_menu_option(self, number: str, description: str, status: str = None):
        """Print a formatted menu option"""
        if status:
            status_color = (
                Colors.OKGREEN
                if status == "✓"
                else (
                    Colors.WARNING
                    if status == "⚠"
                    else Colors.FAIL if status == "✗" else Colors.ENDC
                )
            )
            print(
                f"{Colors.OKBLUE}│{Colors.ENDC} {Colors.BOLD}{number:>2}{Colors.ENDC}. {description:<50} {status_color}[{status}]{Colors.ENDC}"
            )
        else:
            print(
                f"{Colors.OKBLUE}│{Colors.ENDC} {Colors.BOLD}{number:>2}{Colors.ENDC}. {description}"
            )

    def print_separator(self):
        """Print a menu separator"""
        print(f"{Colors.OKBLUE}├{Colors.ENDC}" + "─" * (self.width - 2))

    def print_footer(self):
        """Print menu footer"""
        print(f"{Colors.OKBLUE}└{Colors.ENDC}" + "─" * (self.width - 2))

    def print_warning(self, message: str):
        """Print a warning message"""
        print(f"\n{Colors.WARNING}⚠ Warning: {message}{Colors.ENDC}")

    def print_success(self, message: str):
        """Print a success message"""
        print(f"\n{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

    def print_error(self, message: str):
        """Print an error message"""
        print(f"\n{Colors.FAIL}✗ Error: {message}{Colors.ENDC}")

    def print_info(self, message: str):
        """Print an info message"""
        print(f"\n{Colors.OKBLUE}ℹ {message}{Colors.ENDC}")

    def get_input(self, prompt: str) -> str:
        """Get user input with formatted prompt"""
        return input(f"{Colors.BOLD}> {prompt}: {Colors.ENDC}").strip()

    def confirm_action(self, message: str) -> bool:
        """Ask for user confirmation with formatted prompt"""
        response = input(f"{Colors.WARNING}? {message} (y/N): {Colors.ENDC}").strip().lower()
        return response in ["y", "yes"]

    def print_contract_info(
        self, name: str, policy_id: str, address: str, balance: float, status: str = "✓"
    ):
        """Print formatted contract information"""
        status_color = (
            Colors.OKGREEN if status == "✓" else Colors.WARNING if status == "⚠" else Colors.FAIL
        )
        print(f"{Colors.OKBLUE}│{Colors.ENDC} {Colors.BOLD}{name:<15}{Colors.ENDC}")
        print(f"{Colors.OKBLUE}│{Colors.ENDC}   Policy ID: {policy_id}")
        print(f"{Colors.OKBLUE}│{Colors.ENDC}   Address:   {address}")
        print(
            f"{Colors.OKBLUE}│{Colors.ENDC}   Balance:   {balance:.6f} ADA {status_color}[{status}]{Colors.ENDC}"
        )
        print(f"{Colors.OKBLUE}│{Colors.ENDC}")

    def print_breadcrumb(self, path: list):
        """Print navigation breadcrumb"""
        breadcrumb = " > ".join(path)
        print(f"{Colors.OKBLUE}📍 {breadcrumb}{Colors.ENDC}")
