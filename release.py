#!/usr/bin/env python3

import re
import subprocess
import sys
from pathlib import Path

def run_command(cmd, capture_output=True):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=True, check=True)
        return result.stdout.strip() if capture_output else None
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Exit code: {e.returncode}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        sys.exit(1)

def get_current_version():
    """Read current version from setup.py"""
    setup_py = Path("setup.py")
    if not setup_py.exists():
        print("Error: setup.py not found in current directory")
        sys.exit(1)
    
    content = setup_py.read_text()
    version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
    if not version_match:
        print("Error: Could not find version in setup.py")
        sys.exit(1)
    
    return version_match.group(1)

def bump_version(version):
    """Bump the minor version number"""
    parts = version.split('.')
    if len(parts) != 3:
        print(f"Error: Version format not supported: {version}")
        sys.exit(1)
    
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        new_patch = patch + 1
        return f"{major}.{minor}.{new_patch}"
    except ValueError:
        print(f"Error: Invalid version format: {version}")
        sys.exit(1)

def update_setup_py(new_version):
    """Update version in setup.py"""
    setup_py = Path("setup.py")
    content = setup_py.read_text()
    
    # Replace version string
    new_content = re.sub(
        r'(version\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>{new_version}\g<3>',
        content
    )
    
    setup_py.write_text(new_content)
    print(f"Updated setup.py version to {new_version}")

def update_readme_changelog(new_version):
    """Add placeholder for new version in README changelog"""
    readme = Path("README.md")
    if not readme.exists():
        print("Warning: README.md not found, skipping changelog update")
        return
    
    content = readme.read_text()
    
    # Look for existing changelog section
    changelog_patterns = [
        r'(## Changelog\s*\n)',
        r'(# Changelog\s*\n)',
        r'(## Changes\s*\n)',
        r'(# Changes\s*\n)',
    ]
    
    new_entry = f"## Version {new_version}\n\n- \n\n"
    
    updated = False
    for pattern in changelog_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            new_content = re.sub(
                pattern,
                rf'\g<1>{new_entry}',
                content,
                flags=re.IGNORECASE
            )
            readme.write_text(new_content)
            print(f"Added changelog placeholder for version {new_version}")
            updated = True
            break
    
    if not updated:
        # Add changelog section at the end
        content += f"\n\n## Changelog\n\n{new_entry}"
        readme.write_text(content)
        print(f"Created new changelog section with placeholder for version {new_version}")

def main():
    print("🚀 Starting release process...")
    
    # Check if we're in a git repository
    run_command("git status", capture_output=False)
    
    # Check if working directory is clean
    status = run_command("git status --porcelain")
    if status:
        print("Error: Working directory is not clean. Please commit or stash changes first.")
        sys.exit(1)
    
    # Get current version
    current_version = get_current_version()
    print(f"📦 Current version: {current_version}")
    
    # Create and push tag
    tag_name = f"release-{current_version}"
    print(f"🏷️  Creating tag: {tag_name}")
    
    run_command(f"git tag {tag_name}")
    run_command(f"git push origin {tag_name}")
    print(f"✅ Tag {tag_name} created and pushed")
    
    # Create GitHub release
    print(f"🎉 Creating GitHub release: {current_version}")
    release_cmd = f'gh release create {tag_name} --title "{current_version}" --notes "Release {current_version}"'
    run_command(release_cmd)
    print(f"✅ GitHub release {current_version} created")
    
    # Bump version
    new_version = bump_version(current_version)
    print(f"⬆️  Bumping version to: {new_version}")
    
    # Update setup.py
    update_setup_py(new_version)
    
    # Update README changelog
    update_readme_changelog(new_version)
    
    # Commit version bump
    run_command("git add setup.py README.md")
    run_command(f'git commit -m "Bump version to {new_version}"')
    run_command("git push")
    print(f"✅ Version bumped to {new_version} and committed")
    
    print(f"\n🎊 Release process complete!")
    print(f"   • Released version {current_version}")
    print(f"   • Next version will be {new_version}")
    print(f"   • GitHub release: https://github.com/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\\([^.]*\\).*/\\1/')/releases/tag/{tag_name}")

if __name__ == "__main__":
    main()