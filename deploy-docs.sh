#!/bin/bash
# Simple script to deploy documentation to terrasacha-docs repository

set -e

echo "📥 Deploying documentation to GitHub..."
echo ""

# Go to the docs folder
cd terrasacha-docs-ready-to-push

# Initialize git
echo "🔧 Initializing git repository..."
git init
git branch -M main

# Add files
echo "📝 Adding files..."
git add .

# Commit
echo "💾 Creating commit..."
git commit -m "Initial documentation setup

- Complete MkDocs documentation with Material theme
- GitHub Actions workflow for auto-deployment
- 22 markdown documentation files
- All configuration files"

# Add remote
echo "🔗 Adding remote..."
git remote add origin https://github.com/SuanBlockchain/terrasacha-docs.git

# Push
echo "⬆️  Pushing to GitHub..."
git push -u origin main

echo ""
echo "✅ SUCCESS!"
echo ""
echo "📖 Next step: Configure GitHub Pages"
echo "   Go to: https://github.com/SuanBlockchain/terrasacha-docs/settings/pages"
echo "   Select: gh-pages branch"
echo "   Click: Save"
echo ""
echo "🌐 Your docs will be live at:"
echo "   https://suanblockchain.github.io/terrasacha-docs/"
echo ""
