#!/usr/bin/env python3
"""
AUTO DEPLOY ULTRA SYSTEM
Automatically copies all Ultra Trading System files to the correct locations
Ensures no duplicates, no misalignment, no errors
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

# Define source workspace directory
WORKSPACE_DIR = Path("/workspace")

# Files to copy with their destinations
FILES_TO_DEPLOY = {
    # Core Ultra System Files (root directory)
    "ultra_ml_pipeline.py": "ultra_ml_pipeline.py",
    "ultra_launcher.py": "ultra_launcher.py",
    "ultra_god_mode.py": "ultra_god_mode.py",
    "ultra_moon_spotter.py": "ultra_moon_spotter.py",
    "ultra_forex_master.py": "ultra_forex_master.py",
    "ultra_telegram_master.py": "ultra_telegram_master.py",
    "ultra_scout.py": "ultra_scout.py",  # This replaces the existing one

    # Configuration Files (root directory)
    "requirements_ultra.txt": "requirements_ultra.txt",
    "start_ultra.sh": "start_ultra.sh",
    "telegram_config.json": "telegram_config.json",

    # Documentation (root directory)
    "README_ULTRA.md": "README_ULTRA.md",
    "TELEGRAM_SETUP.md": "TELEGRAM_SETUP.md",

    # Tools Directory Files
    "tools/market_data.py": "tools/market_data.py",
    "tools/ultra_trainer.py": "tools/ultra_trainer.py",
}

def create_backup(target_dir: Path):
    """Create a backup of existing files before deployment."""
    backup_dir = target_dir / f"backup_before_ultra_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # List of files that might be overwritten
    files_to_backup = ["ultra_scout.py"]  # Only this file exists and will be replaced

    backup_needed = False
    for file in files_to_backup:
        file_path = target_dir / file
        if file_path.exists():
            backup_needed = True
            break

    if backup_needed:
        backup_dir.mkdir(exist_ok=True)
        print(f"📦 Creating backup in: {backup_dir}")

        for file in files_to_backup:
            file_path = target_dir / file
            if file_path.exists():
                shutil.copy2(file_path, backup_dir / file)
                print(f"  ✅ Backed up: {file}")

    return backup_dir if backup_needed else None

def deploy_files(target_dir: Path):
    """Deploy all Ultra System files to target directory."""

    print("\n" + "="*70)
    print("🚀 ULTRA TRADING SYSTEM - AUTOMATIC DEPLOYMENT")
    print("="*70)

    # Check if target directory exists
    if not target_dir.exists():
        print(f"❌ ERROR: Target directory does not exist: {target_dir}")
        print("📝 Please create the directory or check the path")
        return False

    print(f"\n📍 Target Directory: {target_dir}")
    print(f"📂 Source Directory: {WORKSPACE_DIR}")

    # Create backup
    backup_dir = create_backup(target_dir)

    # Ensure tools directory exists
    tools_dir = target_dir / "tools"
    if not tools_dir.exists():
        tools_dir.mkdir(parents=True)
        print(f"\n📁 Created tools directory: {tools_dir}")

    # Deploy files
    print("\n📋 Deploying Ultra System Files:")
    print("-" * 50)

    success_count = 0
    error_count = 0

    for source_file, dest_file in FILES_TO_DEPLOY.items():
        source_path = WORKSPACE_DIR / source_file
        dest_path = target_dir / dest_file

        try:
            if not source_path.exists():
                print(f"  ⚠️  SKIP: {source_file} (source not found)")
                continue

            # Create destination directory if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists
            action = "REPLACE" if dest_path.exists() else "CREATE"

            # Copy file
            shutil.copy2(source_path, dest_path)

            # Make shell scripts executable
            if dest_file.endswith('.sh'):
                os.chmod(dest_path, 0o755)

            file_size = source_path.stat().st_size / 1024  # KB
            print(f"  ✅ {action:8} {dest_file:40} ({file_size:.1f} KB)")
            success_count += 1

        except Exception as e:
            print(f"  ❌ ERROR: {dest_file} - {str(e)}")
            error_count += 1

    print("-" * 50)
    print("\n📊 Deployment Summary:")
    print(f"  ✅ Success: {success_count} files")
    print(f"  ❌ Errors: {error_count} files")

    if backup_dir:
        print(f"\n💾 Backup Location: {backup_dir}")

    # Verify critical files
    print("\n🔍 Verifying Critical Files:")
    critical_files = [
        "ultra_launcher.py",
        "ultra_ml_pipeline.py",
        "tools/ultra_trainer.py",
        "tools/market_data.py"
    ]

    all_critical_present = True
    for file in critical_files:
        file_path = target_dir / file
        if file_path.exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} - MISSING!")
            all_critical_present = False

    if all_critical_present and error_count == 0:
        print("\n" + "="*70)
        print("✨ DEPLOYMENT SUCCESSFUL! ✨")
        print("="*70)
        print("\n🎯 Next Steps:")
        print("1. Navigate to your project directory:")
        print(f"   cd {target_dir}")
        print("\n2. Install Python dependencies:")
        print("   pip install -r requirements_ultra.txt")
        print("\n3. Configure Telegram (optional):")
        print("   Edit telegram_config.json with your bot token")
        print("\n4. Run the Ultra System:")
        print("   python ultra_launcher.py --mode paper --train --god-mode --moon-spotter --forex")
        print("\n   Or use the start script:")
        print("   ./start_ultra.sh  (Linux/Mac)")
        print("   bash start_ultra.sh  (Windows Git Bash)")
        return True
    else:
        print("\n⚠️ DEPLOYMENT COMPLETED WITH ISSUES")
        print("Please check the errors above and try again")
        return False

def copy_to_windows_style_path():
    """Handle Windows-style path and copy files."""

    # Common Windows paths to check
    possible_paths = [
        Path("C:/Users/User/Downloads/LeanTrader_ForexPack"),
        Path("/mnt/c/Users/User/Downloads/LeanTrader_ForexPack"),  # WSL path
        Path("~/Downloads/LeanTrader_ForexPack").expanduser(),
        Path("./").resolve(),  # Current directory
    ]

    print("\n🔍 Searching for project directory...")

    target_dir = None
    for path in possible_paths:
        if path.exists():
            # Check if it looks like the right project
            if (path / "ultra_core.py").exists() or (path / "ultra_scout.py").exists():
                target_dir = path
                print(f"✅ Found project directory: {target_dir}")
                break
            else:
                print(f"  Checked: {path} (not the project)")

    if not target_dir:
        # Try current workspace as target
        if (WORKSPACE_DIR / "ultra_core.py").exists():
            target_dir = WORKSPACE_DIR
            print(f"📍 Using workspace as target: {target_dir}")

    if target_dir:
        return deploy_files(target_dir)
    else:
        print("\n❌ Could not find project directory automatically")
        print("\n📝 Manual Option:")
        print("Please specify your project path by editing this script")
        print("or copy files manually from /workspace/ to your project")
        return False

def main():
    """Main deployment function."""

    # First, let's copy everything within the workspace to ensure consistency
    print("\n🔧 PREPARING ULTRA SYSTEM DEPLOYMENT")
    print("="*70)

    # Since we're in the workspace, deploy files here first
    success = deploy_files(WORKSPACE_DIR)

    if success:
        print("\n✅ ALL FILES DEPLOYED SUCCESSFULLY!")
        print("\n📌 Files are now in: /workspace/")
        print("\n📥 To get files to your Windows folder:")
        print("   1. Download the files from /workspace/")
        print("   2. Or use Git to sync if this is a Git repository")
        print("   3. Or use any file transfer method you prefer")

        # Create a ZIP file for easy download
        print("\n📦 Creating ZIP archive for easy download...")
        import zipfile

        zip_path = WORKSPACE_DIR / "ultra_system_complete.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for source_file in FILES_TO_DEPLOY.keys():
                source_path = WORKSPACE_DIR / source_file
                if source_path.exists():
                    zipf.write(source_path, source_file)

        print(f"✅ Created: {zip_path}")
        print(f"   Size: {zip_path.stat().st_size / 1024:.1f} KB")
        print("\n💡 Download this ZIP file and extract to your Windows project folder!")

    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
