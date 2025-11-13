# Terrasacha Contracts Documentation

Official documentation for the Terrasacha Contracts project - Cardano smart contracts for carbon credit tokens and NFTs built with OpShin.

## 📚 Documentation Site

Visit our documentation at: [https://suanblockchain.github.io/terrasacha-docs/](https://suanblockchain.github.io/terrasacha-docs/)

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Installation

1. Clone this repository:
```bash
git clone https://github.com/SuanBlockchain/terrasacha-docs.git
cd terrasacha-docs
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running Locally

Start the development server:

```bash
mkdocs serve
```

The documentation will be available at `http://127.0.0.1:8000/`

## 📖 Documentation Structure

```
docs/
├── index.md                    # Homepage
├── getting-started/           # Getting started guides
│   ├── installation.md
│   ├── quickstart.md
│   └── development.md
├── architecture/              # Architecture documentation
│   ├── overview.md
│   ├── validators.md
│   ├── minting-policies.md
│   └── types.md
├── contracts/                 # Contract specifications
│   ├── protocol-validator.md
│   ├── protocol-nfts.md
│   ├── details.md
│   └── validations.md
├── api/                       # API Reference
│   ├── validators.md
│   ├── minting-policies.md
│   ├── types.md
│   └── utilities.md
├── testing/                   # Testing documentation
│   ├── overview.md
│   └── running-tests.md
└── development/               # Development guides
    ├── build-system.md
    ├── cli-tools.md
    ├── claude-guide.md
    └── contributing.md
```

## ✏️ Contributing

### Making Changes

1. Create a new branch:
```bash
git checkout -b docs/your-feature-name
```

2. Make your changes to the markdown files

3. Preview your changes locally:
```bash
mkdocs serve
```

4. Commit and push:
```bash
git add .
git commit -m "docs: your meaningful commit message"
git push origin docs/your-feature-name
```

5. Create a Pull Request

### Writing Guidelines

- Use clear, concise language
- Include code examples where appropriate
- Add diagrams or images to explain complex concepts
- Follow the existing documentation structure
- Test all code examples before committing

## 🔨 Building

Build the static site:

```bash
mkdocs build
```

The built site will be in the `site/` directory.

## 🚢 Deployment

The documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` branch using GitHub Actions.

### Manual Deployment

```bash
mkdocs gh-deploy
```

## 📝 MkDocs Configuration

This documentation uses:

- **Theme**: Material for MkDocs
- **Features**:
  - Navigation tabs and sections
  - Search functionality
  - Code copy buttons
  - Dark/Light mode toggle
- **Extensions**:
  - Syntax highlighting
  - Admonitions
  - Task lists
  - Emojis
  - And more...

See `mkdocs.yml` for complete configuration.

## 🔗 Links

- **Main Repository**: [SuanBlockchain/terrasacha-contracts](https://github.com/SuanBlockchain/terrasacha-contracts)
- **Documentation Site**: [https://suanblockchain.github.io/terrasacha-docs/](https://suanblockchain.github.io/terrasacha-docs/)

## 📄 License

Copyright © 2024 Terrasacha

## 🤝 Support

For questions or issues related to the documentation, please open an issue in this repository.

For questions about the contracts themselves, please visit the [main repository](https://github.com/SuanBlockchain/terrasacha-contracts).
