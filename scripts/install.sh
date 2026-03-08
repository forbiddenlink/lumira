#!/bin/bash
# AI Artist - Installation Script
# Automates the setup process for new installations

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_msg() {
    echo -e "${2}${1}${NC}"
}

print_msg "🎨 AI Artist Installation Script" "$BLUE"
print_msg "=================================" "$BLUE"
echo ""

# Check Python version
print_msg "Checking Python version..." "$YELLOW"
PYTHON_VERSION=$(python --version 2>&1 | grep -oP '\d+\.\d+' || python3 --version 2>&1 | grep -oP '\d+\.\d+')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    print_msg "❌ Python 3.11+ required. Found: $PYTHON_VERSION" "$RED"
    exit 1
fi
print_msg "✅ Python $PYTHON_VERSION found" "$GREEN"
echo ""

# Detect system
print_msg "Detecting system..." "$YELLOW"
OS=$(uname -s)
ARCH=$(uname -m)
print_msg "✅ Running on $OS ($ARCH)" "$GREEN"
echo ""

# Create virtual environment
if [ ! -d "venv" ]; then
    print_msg "Creating virtual environment..." "$YELLOW"
    python -m venv venv
    print_msg "✅ Virtual environment created" "$GREEN"
else
    print_msg "⚠️  Virtual environment already exists" "$YELLOW"
fi
echo ""

# Activate virtual environment
print_msg "Activating virtual environment..." "$YELLOW"
source venv/bin/activate
print_msg "✅ Virtual environment activated" "$GREEN"
echo ""

# Upgrade pip
print_msg "Upgrading pip..." "$YELLOW"
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
print_msg "✅ pip upgraded" "$GREEN"
echo ""

# Install PyTorch based on system
print_msg "Installing PyTorch..." "$YELLOW"
if [[ "$OS" == "Darwin" ]] && [[ "$ARCH" == "arm64" ]]; then
    # Apple Silicon
    print_msg "Detected Apple Silicon - Installing MPS-optimized PyTorch" "$BLUE"
    pip install torch torchvision torchaudio
elif command -v nvidia-smi &> /dev/null; then
    # NVIDIA GPU detected
    print_msg "NVIDIA GPU detected - Installing CUDA 11.8 PyTorch" "$BLUE"
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
else
    # CPU only
    print_msg "No GPU detected - Installing CPU-only PyTorch" "$BLUE"
    pip install torch torchvision torchaudio
fi
print_msg "✅ PyTorch installed" "$GREEN"
echo ""

# Install requirements
print_msg "Installing dependencies..." "$YELLOW"
pip install -r requirements.txt
print_msg "✅ Dependencies installed" "$GREEN"
echo ""

# Install package in editable mode
print_msg "Installing AI Artist package..." "$YELLOW"
pip install -e .
print_msg "✅ Package installed" "$GREEN"
echo ""

# Create config file if it doesn't exist
if [ ! -f "config/config.yaml" ]; then
    print_msg "Creating config file..." "$YELLOW"
    cp config/config.example.yaml config/config.yaml
    print_msg "✅ Config file created" "$GREEN"
else
    print_msg "⚠️  Config file already exists" "$YELLOW"
fi
echo ""

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_msg "Creating .env file..." "$YELLOW"
    cp .env.example .env
    print_msg "✅ .env file created" "$GREEN"
    print_msg "⚠️  Remember to add your API keys to .env!" "$YELLOW"
else
    print_msg "⚠️  .env file already exists" "$YELLOW"
fi
echo ""

# Create necessary directories
print_msg "Creating directories..." "$YELLOW"
mkdir -p data logs models/cache models/lora gallery datasets/training datasets/regularization
print_msg "✅ Directories created" "$GREEN"
echo ""

# Run database migrations
print_msg "Setting up database..." "$YELLOW"
alembic upgrade head
print_msg "✅ Database initialized" "$GREEN"
echo ""

# Install pre-commit hooks (optional)
read -p "Install pre-commit hooks for development? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_msg "Installing pre-commit hooks..." "$YELLOW"
    pre-commit install
    print_msg "✅ Pre-commit hooks installed" "$GREEN"
fi
echo ""

# Run verification
print_msg "Running verification tests..." "$YELLOW"
python -c "import ai_artist; print('✅ Package import successful')"
python -c "import torch; print(f'✅ PyTorch version: {torch.__version__}')"
python -c "import torch; print(f'✅ CUDA available: {torch.cuda.is_available()}')" || true
python -c "import torch; print(f'✅ MPS available: {torch.backends.mps.is_available()}')" || true
echo ""

# Final message
print_msg "=================================" "$GREEN"
print_msg "🎉 Installation Complete!" "$GREEN"
print_msg "=================================" "$GREEN"
echo ""
print_msg "Next steps:" "$BLUE"
echo "1. Edit config/config.yaml with your API keys"
echo "2. Edit .env with your sensitive credentials"
echo "3. Read QUICKSTART.md for usage examples"
echo ""
print_msg "Quick commands:" "$BLUE"
echo "  lumira --theme 'your prompt'  # Generate artwork"
echo "  lumira-web                     # Launch web gallery"
echo "  lumira-schedule start daily    # Start automation"
echo ""
print_msg "Need help? Check TROUBLESHOOTING.md" "$YELLOW"
echo ""
print_msg "Happy creating! 🎨" "$GREEN"
