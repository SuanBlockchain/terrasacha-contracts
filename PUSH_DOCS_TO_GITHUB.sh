#!/bin/bash

# This script will push the documentation to the new GitHub repository
# Make sure you've created the repository at: https://github.com/SuanBlockchain/terrasacha-docs

set -e  # Exit on any error

echo "🚀 Pushing Terrasacha Documentation to GitHub"
echo "=============================================="
echo ""

# Check if terrasacha-docs-ready-to-push exists
if [ ! -d "terrasacha-docs-ready-to-push" ]; then
    echo "❌ Error: terrasacha-docs-ready-to-push folder not found!"
    echo "Please run this script from the terrasacha-contracts directory."
    exit 1
fi

# Create a temporary directory
TEMP_DIR=$(mktemp -d)
echo "📁 Creating temporary directory: $TEMP_DIR"

# Copy files to temp directory
echo "📋 Copying documentation files..."
cp -r terrasacha-docs-ready-to-push/* "$TEMP_DIR/"
cp -r terrasacha-docs-ready-to-push/.github "$TEMP_DIR/"
cp terrasacha-docs-ready-to-push/.gitignore "$TEMP_DIR/"

# Initialize git repository
cd "$TEMP_DIR"
echo "🔧 Initializing git repository..."
git init
git branch -M main

# Add all files
echo "📝 Adding files to git..."
git add .

# Create initial commit
echo "💾 Creating initial commit..."
git commit -m "Initial documentation setup

- Extracted all documentation from terrasacha-contracts
- Set up MkDocs with Material theme
- Added GitHub Actions for automatic deployment
- Configured for GitHub Pages hosting

Documentation structure:
- 22 markdown files organized in 6 categories
- Custom CSS styling
- Complete navigation setup
- Search and highlighting enabled"

# Add remote
echo "🔗 Adding GitHub remote..."
git remote add origin https://github.com/SuanBlockchain/terrasacha-docs.git

# Push to GitHub
echo "⬆️  Pushing to GitHub..."
git push -u origin main

echo ""
echo "✅ SUCCESS! Documentation pushed to GitHub"
echo ""
echo "📖 Next steps:"
echo "1. Go to: https://github.com/SuanBlockchain/terrasacha-docs/settings/pages"
echo "2. Under 'Source', select 'Deploy from a branch'"
echo "3. Under 'Branch', select 'gh-pages' and '/ (root)'"
echo "4. Click 'Save'"
echo ""
echo "🌐 Your documentation will be live at:"
echo "   https://suanblockchain.github.io/terrasacha-docs/"
echo ""
echo "🔥 Cleaning up temporary directory..."
cd -
rm -rf "$TEMP_DIR"

echo ""
echo "✨ All done!"
