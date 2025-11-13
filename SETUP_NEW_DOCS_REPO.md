# Setting Up the Terrasacha Documentation Repository

This guide will walk you through creating a new dedicated documentation repository under SuanBlockchain.

## Step 1: Extract Documentation Files

Run the extraction script from the current repository:

```bash
./extract-docs.sh ../terrasacha-docs
```

This will create a new directory `../terrasacha-docs` with all the documentation files.

## Step 2: Set Up the New Repository Directory

```bash
cd ../terrasacha-docs
```

## Step 3: Add Additional Files

Copy the prepared files from the original repository:

```bash
# Copy README
cp ../terrasacha-contracts/DOCS_README.md ./README.md

# Copy requirements.txt
cp ../terrasacha-contracts/DOCS_requirements.txt ./requirements.txt

# Copy updated mkdocs.yml (overwrite the existing one)
cp ../terrasacha-contracts/DOCS_mkdocs.yml ./mkdocs.yml

# Create .github/workflows directory
mkdir -p .github/workflows

# Copy GitHub Actions workflow
cp ../terrasacha-contracts/DOCS_github_actions.yml .github/workflows/deploy.yml
```

## Step 4: Create .gitignore

Create a `.gitignore` file:

```bash
cat > .gitignore << 'EOF'
# MkDocs
site/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
EOF
```

## Step 5: Create the GitHub Repository

Go to GitHub and create a new repository:

1. Go to https://github.com/organizations/SuanBlockchain/repositories/new
2. Repository name: `terrasacha-docs`
3. Description: "Documentation for Terrasacha Contracts - Cardano smart contracts for carbon credit tokens and NFTs"
4. Visibility: Public (or Private, depending on your preference)
5. Do NOT initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"

## Step 6: Initialize Git and Push

```bash
# Initialize git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial documentation setup

- Extracted all documentation from terrasacha-contracts
- Set up MkDocs with Material theme
- Added GitHub Actions for automatic deployment
- Configured for GitHub Pages hosting"

# Rename branch to main (if needed)
git branch -M main

# Add remote origin (replace with your actual repository URL)
git remote add origin https://github.com/SuanBlockchain/terrasacha-docs.git

# Push to GitHub
git push -u origin main
```

## Step 7: Configure GitHub Pages

1. Go to your repository settings: https://github.com/SuanBlockchain/terrasacha-docs/settings/pages
2. Under "Source", select "Deploy from a branch"
3. Under "Branch", select `gh-pages` and `/ (root)`
4. Click "Save"

**Note**: The `gh-pages` branch will be created automatically by the GitHub Actions workflow after the first push to main.

## Step 8: Verify Deployment

After pushing to main:

1. Go to the "Actions" tab in your repository
2. You should see the "Deploy Documentation" workflow running
3. Once complete, your documentation will be available at:
   https://suanblockchain.github.io/terrasacha-docs/

## Step 9: Test Locally (Optional but Recommended)

Before pushing, you can test the documentation locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Serve locally
mkdocs serve
```

Visit http://127.0.0.1:8000 to preview the documentation.

## Step 10: Update the Original Repository

After successfully creating the documentation repository, you should update the original `terrasacha-contracts` repository:

1. Update the README to reference the new documentation repository
2. Consider removing the `docs/` directory from the main repository (optional)
3. Add a link to the documentation site in the main README

Example addition to the main README:

```markdown
## 📚 Documentation

Full documentation is available at [https://suanblockchain.github.io/terrasacha-docs/](https://suanblockchain.github.io/terrasacha-docs/)

Documentation repository: [SuanBlockchain/terrasacha-docs](https://github.com/SuanBlockchain/terrasacha-docs)
```

## Maintenance

### Updating Documentation

To update the documentation:

1. Clone the repository
2. Make changes to markdown files in the `docs/` directory
3. Test locally with `mkdocs serve`
4. Commit and push to main
5. GitHub Actions will automatically deploy the changes

### Adding New Pages

1. Create a new markdown file in the appropriate `docs/` subdirectory
2. Add an entry in `mkdocs.yml` under the `nav:` section
3. Commit and push

## Troubleshooting

### GitHub Actions fails

- Check the Actions tab for error messages
- Ensure `requirements.txt` includes all necessary dependencies
- Verify that the `gh-pages` branch is configured in repository settings

### Documentation not updating

- Clear your browser cache
- Wait a few minutes (GitHub Pages can take time to update)
- Check the Actions tab to ensure deployment succeeded

### Local development issues

- Ensure Python 3.8+ is installed
- Try creating a virtual environment:
  ```bash
  python -m venv venv
  source venv/bin/activate  # On Windows: venv\Scripts\activate
  pip install -r requirements.txt
  ```

## Additional Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
