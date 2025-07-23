#!/bin/bash

set -euo pipefail

# Default values
DEFAULT_ACTION=""
VERBOSE=false
DRY_RUN=false

# Function to show usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] STAGING_DIR TARGET_DIR

Safely merge files from staging directory to target directory.

Arguments:
    STAGING_DIR    Source directory containing files to merge
    TARGET_DIR     Destination directory to merge files into

Options:
    -d, --default ACTION    Default action for conflicts: replace, skip, backup
    -v, --verbose          Enable verbose output
    -n, --dry-run          Show what would be done without making changes
    -h, --help             Show this help message

Examples:
    $0 /tmp/incoming /home/user/photos
    $0 --default skip /tmp/incoming /home/user/photos
    $0 --dry-run --verbose /tmp/incoming /home/user/photos
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--default)
            DEFAULT_ACTION="$2"
            if [[ ! "$DEFAULT_ACTION" =~ ^(replace|skip|backup)$ ]]; then
                echo "Error: Invalid default action. Must be: replace, skip, or backup"
                exit 1
            fi
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Error: Unknown option $1"
            usage
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

# Check required arguments
if [ $# -ne 2 ]; then
    echo "Error: Missing required arguments"
    usage
    exit 1
fi

STAGING_DIR="$1"
TARGET_DIR="$2"
LOG_FILE="/tmp/merge_$(basename "$TARGET_DIR")_$(date +%Y%m%d_%H%M%S).log"

# Verbose logging function
log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo "$1"
    fi
}

# Function to get file info
get_file_info() {
    local file="$1"
    local size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo "0")
    local mime=$(file -b --mime-type "$file" 2>/dev/null || echo "unknown")
    echo "Size: ${size} bytes, Type: ${mime}"
}

# Function to compare and prompt for conflicts
handle_conflict() {
    local src_file="$1"
    local dst_file="$2"
    local rel_path="$3"
    
    echo "CONFLICT: File exists in both locations"
    echo "File: $rel_path"
    echo "Source: $src_file"
    get_file_info "$src_file"
    echo "Target: $dst_file" 
    get_file_info "$dst_file"
    
    # Generate checksums
    local src_md5=$(md5sum "$src_file" 2>/dev/null | cut -d' ' -f1 || md5 -q "$src_file" 2>/dev/null)
    local dst_md5=$(md5sum "$dst_file" 2>/dev/null | cut -d' ' -f1 || md5 -q "$dst_file" 2>/dev/null)
    
    if [ "$src_md5" = "$dst_md5" ]; then
        echo "Files are identical (same MD5), skipping..."
        log_verbose "Identical files skipped: $rel_path"
        return 0
    fi
    
    echo "Files differ (different MD5)"
    echo "Source MD5: $src_md5"
    echo "Target MD5: $dst_md5"
    
    local choice=""
    
    # Use default action if specified
    if [ -n "$DEFAULT_ACTION" ]; then
        case "$DEFAULT_ACTION" in
            replace) choice="r" ;;
            skip) choice="s" ;;
            backup) choice="b" ;;
        esac
        echo "Using default action: $DEFAULT_ACTION"
    else
        echo "Options: [r]eplace, [s]kip, [b]ackup and replace, [q]uit"
        read -p "Choice: " choice
    fi
    
    case $choice in
        r|R)
            if [ "$DRY_RUN" = true ]; then
                echo "[DRY RUN] Would replace: $dst_file"
            else
                cp "$src_file" "$dst_file"
                echo "Replaced: $rel_path" | tee -a "$LOG_FILE"
            fi
            ;;
        s|S)
            echo "Skipped: $rel_path" | tee -a "$LOG_FILE"
            ;;
        b|B)
            if [ "$DRY_RUN" = true ]; then
                echo "[DRY RUN] Would backup and replace: $dst_file"
            else
                cp "$dst_file" "${dst_file}.backup.$(date +%s)"
                cp "$src_file" "$dst_file"
                echo "Backed up and replaced: $rel_path" | tee -a "$LOG_FILE"
            fi
            ;;
        q|Q)
            echo "Merge cancelled by user"
            exit 1
            ;;
        *)
            echo "Invalid choice, skipping file"
            echo "Skipped: $rel_path" | tee -a "$LOG_FILE"
            ;;
    esac
}

# Main merge function
merge_files() {
    echo "Starting merge from $STAGING_DIR to $TARGET_DIR"
    echo "Log file: $LOG_FILE"
    
    if [ "$DRY_RUN" = true ]; then
        echo "DRY RUN MODE - No files will be modified"
    fi
    
    local file_count=0
    local conflict_count=0
    local copied_count=0
    
    # Find all files in staging directory
    while IFS= read -r -d '' src_file; do
        # Calculate relative path
        rel_path="${src_file#$STAGING_DIR/}"
        dst_file="$TARGET_DIR/$rel_path"
        dst_dir=$(dirname "$dst_file")
        
        log_verbose "Processing: $rel_path"
        
        # Create destination directory if needed
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY RUN] Would create directory: $dst_dir"
        else
            mkdir -p "$dst_dir"
        fi
        
        if [ -f "$dst_file" ]; then
            ((conflict_count++))
            handle_conflict "$src_file" "$dst_file" "$rel_path"
        else
            # File doesn't exist, safe to copy
            if [ "$DRY_RUN" = true ]; then
                echo "[DRY RUN] Would copy: $rel_path"
            else
                cp "$src_file" "$dst_file"
                echo "Copied: $rel_path" | tee -a "$LOG_FILE"
            fi
            ((copied_count++))
        fi
        
        ((file_count++))
    done < <(find "$STAGING_DIR" -type f -print0)
    
    echo ""
    echo "Merge summary:"
    echo "  Total files processed: $file_count"
    echo "  Files copied: $copied_count"
    echo "  Conflicts encountered: $conflict_count"
    
    if [ "$DRY_RUN" = false ]; then
        echo "  Log file: $LOG_FILE"
    fi
}

# Verify staging directory exists
if [ ! -d "$STAGING_DIR" ]; then
    echo "Error: Staging directory $STAGING_DIR does not exist"
    exit 1
fi

# Create target directory if needed
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would create target directory: $TARGET_DIR"
else
    mkdir -p "$TARGET_DIR"
fi

# Run merge
merge_files

echo "Merge complete."