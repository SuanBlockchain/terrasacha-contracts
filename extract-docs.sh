#!/bin/bash

# Script to extract documentation files for a new dedicated documentation repository
# Usage: ./extract-docs.sh [output-directory]

OUTPUT_DIR="${1:-../terrasacha-docs}"

echo "Extracting documentation to: $OUTPUT_DIR"

# Create output directory structure
mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/docs"

# Copy documentation files
echo "Copying markdown files..."
cp -r docs/* "$OUTPUT_DIR/docs/"

# Copy mkdocs configuration
echo "Copying mkdocs.yml..."
cp mkdocs.yml "$OUTPUT_DIR/"

echo ""
echo "Documentation extracted successfully to: $OUTPUT_DIR"
echo ""
echo "Files copied:"
echo "  - mkdocs.yml (configuration)"
echo "  - docs/ (all markdown files and assets)"
echo ""
echo "Next steps:"
echo "  1. cd $OUTPUT_DIR"
echo "  2. Create a new GitHub repository: terrasacha-docs"
echo "  3. Initialize git: git init"
echo "  4. Add files: git add ."
echo "  5. Commit: git commit -m 'Initial documentation setup'"
echo "  6. Add remote: git remote add origin https://github.com/SuanBlockchain/terrasacha-docs.git"
echo "  7. Push: git push -u origin main"
