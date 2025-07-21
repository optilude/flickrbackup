#!/bin/bash

# Script to move files from set directories to top-level date directories
# Usage: ./move_favorites_to_date_dirs.sh [directory]
# If no directory specified, uses current directory

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the target directory (default to current directory)
TARGET_DIR="${1:-.}"

# Validate directory exists
if [[ ! -d "$TARGET_DIR" ]]; then
    echo -e "${RED}Error: Directory '$TARGET_DIR' does not exist${NC}"
    exit 1
fi

echo -e "${BLUE}Moving files from set directories to top-level date directories...${NC}"
echo -e "${BLUE}Target directory: $(realpath "$TARGET_DIR")${NC}"
echo

# Function to get file size in bytes
get_file_size() {
    if [[ -f "$1" ]]; then
        # Use stat command (works on both Linux and macOS)
        if stat -c%s "$1" 2>/dev/null; then
            return  # Linux
        elif stat -f%z "$1" 2>/dev/null; then
            return  # macOS
        else
            echo "unknown"
        fi
    else
        echo "0"
    fi
}

# Function to format file size for display
format_file_size() {
    local size=$1
    if [[ "$size" == "unknown" ]]; then
        echo "unknown size"
    elif [[ $size -lt 1024 ]]; then
        echo "${size} bytes"
    elif [[ $size -lt 1048576 ]]; then
        echo "$(( size / 1024 )) KB"
    else
        echo "$(( size / 1048576 )) MB"
    fi
}

# Counters
moved_files=0
skipped_files=0
conflicts=0

# Find all files in set directories (pattern: SET_NAME/YYYY/MM/DD/*)
# We look for directories that match the pattern and contain files
while IFS= read -r -d '' set_date_dir; do
    # Extract the date path (YYYY/MM/DD) from the full path
    if [[ "$set_date_dir" =~ ([0-9]{4}/[0-9]{2}/[0-9]{2})$ ]]; then
        date_path="${BASH_REMATCH[1]}"
        
        # Skip if this is already a top-level date directory (not inside a set)
        # Check if the path before the date is just the target directory
        set_name_part="${set_date_dir%/$date_path}"
        if [[ "$set_name_part" == "$TARGET_DIR" ]]; then
            continue  # Skip top-level date directories
        fi
        
        # Create top-level date directory if it doesn't exist
        top_level_date_dir="$TARGET_DIR/$date_path"
        mkdir -p "$top_level_date_dir"
        
        echo -e "${YELLOW}Processing: $set_date_dir${NC}"
        
        # Find all files in this set date directory
        while IFS= read -r -d '' file; do
            filename=$(basename "$file")
            destination="$top_level_date_dir/$filename"
            
            if [[ -f "$destination" ]]; then
                # File exists in destination - compare sizes and warn
                source_size=$(get_file_size "$file")
                dest_size=$(get_file_size "$destination")
                
                echo -e "  ${RED}CONFLICT:${NC} $filename"
                echo -e "    Set file:  $(format_file_size "$source_size") - $file"
                echo -e "    Date file: $(format_file_size "$dest_size") - $destination"
                
                if [[ "$source_size" == "$dest_size" ]]; then
                    echo -e "    ${GREEN}Files are same size - removing duplicate from set directory${NC}"
                    rm "$file"
                    ((moved_files++))
                else
                    echo -e "    ${YELLOW}Files are different sizes - keeping both (manual review needed)${NC}"
                    ((conflicts++))
                fi
            else
                # Safe to move
                mv "$file" "$destination"
                echo -e "  ${GREEN}Moved:${NC} $filename"
                ((moved_files++))
            fi
        done < <(find "$set_date_dir" -maxdepth 1 -type f -print0)
        
        # Remove empty set date directory if it's now empty
        if [[ -d "$set_date_dir" ]] && [[ -z "$(ls -A "$set_date_dir")" ]]; then
            rmdir "$set_date_dir"
            echo -e "  ${BLUE}Removed empty directory: $set_date_dir${NC}"
        fi
        
    fi
done < <(find "$TARGET_DIR" -type d -path "*/[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]" -print0)

# Now clean up empty set directories
echo
echo -e "${BLUE}Cleaning up empty set directories...${NC}"

# Find and remove empty year directories within sets
find "$TARGET_DIR" -type d -path "*/[0-9][0-9][0-9][0-9]/[0-9][0-9]" -empty -delete 2>/dev/null || true
find "$TARGET_DIR" -type d -path "*/[0-9][0-9][0-9][0-9]" -empty -delete 2>/dev/null || true

# Find and remove empty set directories (but not top-level date directories)
while IFS= read -r -d '' empty_dir; do
    # Don't remove if it's a top-level date directory (YYYY, YYYY/MM, or YYYY/MM/DD)
    if [[ ! "$empty_dir" =~ ^$TARGET_DIR/[0-9]{4}(/[0-9]{2}(/[0-9]{2})?)?$ ]]; then
        if [[ -d "$empty_dir" ]] && [[ -z "$(ls -A "$empty_dir")" ]]; then
            rmdir "$empty_dir" 2>/dev/null || true
            echo -e "  ${BLUE}Removed empty set directory: $empty_dir${NC}"
        fi
    fi
done < <(find "$TARGET_DIR" -type d -empty -print0 2>/dev/null)

echo
echo -e "${GREEN}Summary:${NC}"
echo -e "  Files moved/deduplicated: $moved_files"
echo -e "  Files with conflicts (need manual review): $conflicts"

if [[ $conflicts -gt 0 ]]; then
    echo
    echo -e "${YELLOW}Please manually review the conflicting files listed above.${NC}"
    echo -e "${YELLOW}They have different sizes and may be different versions of the same photo.${NC}"
    exit 1
else
    echo -e "${GREEN}All files processed successfully!${NC}"
fi
