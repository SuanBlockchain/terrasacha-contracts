# How to Extract and Use the Documentation Repository

## 📦 What You Have

I've created a compressed archive: `terrasacha-docs.tar.gz` (88KB)

This archive contains the complete documentation repository ready to deploy.

---

## 🚀 How to Use It

### Step 1: Download from GitHub

```bash
# Clone or pull your branch
git clone https://github.com/SuanBlockchain/terrasacha-contracts.git
cd terrasacha-contracts
git checkout claude/create-new-repository-01PtKbLrhZyXSkZYPSfRt5b4

# Or if you already have it cloned
git pull origin claude/create-new-repository-01PtKbLrhZyXSkZYPSfRt5b4
```

You should now see `terrasacha-docs.tar.gz` in your local directory.

### Step 2: Extract the Archive

```bash
# Extract in the parent directory (one level up from terrasacha-contracts)
cd ..
tar -xzf terrasacha-contracts/terrasacha-docs.tar.gz

# You should now have a new folder: terrasacha-docs/
ls -la terrasacha-docs/
```

Or extract anywhere you want:

```bash
# Extract to a specific location
tar -xzf terrasacha-docs.tar.gz -C /path/where/you/want
```

### Step 3: Navigate to the New Repository

```bash
cd terrasacha-docs
ls -la
```

You should see:
```
.git/
.github/
.gitignore
README.md
REPOSITORY_CREATION_SUMMARY.md
docs/
mkdocs.yml
requirements.txt
```

### Step 4: Verify the Repository

```bash
# Check git status
git status

# View the commit
git log --oneline

# List all documentation files
find docs -name "*.md"
```

---

## 🌐 Deploy to GitHub

### Step 1: Create GitHub Repository

1. Go to: https://github.com/organizations/SuanBlockchain/repositories/new
2. **Name**: `terrasacha-docs`
3. **Description**: "Documentation for Terrasacha Contracts - Cardano smart contracts for carbon credit tokens and NFTs"
4. **Visibility**: Public
5. **DO NOT** initialize with README
6. Click "Create repository"

### Step 2: Push to GitHub

```bash
# Make sure you're in the terrasacha-docs directory
cd terrasacha-docs

# Add remote
git remote add origin https://github.com/SuanBlockchain/terrasacha-docs.git

# Push
git push -u origin main
```

### Step 3: Configure GitHub Pages

1. Go to: https://github.com/SuanBlockchain/terrasacha-docs/settings/pages
2. **Source**: Deploy from a branch
3. **Branch**: `gh-pages` / `(root)`
4. Click "Save"

### Step 4: Wait for Deployment

- Go to **Actions** tab
- Wait for "Deploy Documentation" workflow to complete
- Visit: **https://suanblockchain.github.io/terrasacha-docs/**

---

## 🧪 Test Locally (Optional)

Before pushing, test the documentation:

```bash
cd terrasacha-docs

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Serve locally
mkdocs serve
```

Visit: http://127.0.0.1:8000

---

## 📋 What's Inside the Archive

- **28 files total**
- **22 markdown documentation files**
- **MkDocs configuration** (Material theme)
- **GitHub Actions workflow** (auto-deployment)
- **requirements.txt** (Python dependencies)
- **README.md** (repository documentation)
- **.gitignore** (properly configured)
- **Complete git repository** (initialized with initial commit)

---

## 🎯 Quick Reference

```bash
# Extract
tar -xzf terrasacha-docs.tar.gz

# Navigate
cd terrasacha-docs

# Add remote and push
git remote add origin https://github.com/SuanBlockchain/terrasacha-docs.git
git push -u origin main
```

---

## 📖 More Information

See `REPOSITORY_CREATION_SUMMARY.md` inside the extracted folder for complete details.

---

## ❓ Troubleshooting

**Q: Where should I extract this?**
A: Anywhere you want! I recommend extracting it next to your `terrasacha-contracts` folder for easy organization.

**Q: The archive won't extract**
A: Make sure you have `tar` installed. On Windows, use WSL or 7-Zip. On Mac/Linux, `tar` is built-in.

**Q: Can I delete the .tar.gz file after extracting?**
A: Yes, once extracted and verified, you can delete `terrasacha-docs.tar.gz`.

**Q: Do I need to keep this in my main repository?**
A: No, the `.tar.gz` file is just for transferring the files to you. Once you've extracted it and pushed to GitHub, you can remove it from your branch if desired.

---

**Ready to deploy your documentation!** 🚀
