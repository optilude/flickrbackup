#!/bin/bash

# Script to find .mov files that likely contain images instead of actual movies
# Usage: ./find_image_movies.sh [directory] [output_file]
# If no directory specified, uses current directory
# If output_file specified, writes photo IDs (filename without extension) to file

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse command line arguments
SEARCH_DIR="${1:-.}"
OUTPUT_FILE="$2"

# Validate directory exists
if [[ ! -d "$SEARCH_DIR" ]]; then
    echo -e "${RED}Error: Directory '$SEARCH_DIR' does not exist${NC}"
    exit 1
fi

echo -e "${BLUE}Scanning for .mov files that likely contain images...${NC}"
echo -e "${BLUE}Search directory: $(realpath "$SEARCH_DIR")${NC}"
if [[ -n "$OUTPUT_FILE" ]]; then
    echo -e "${BLUE}Output file: $OUTPUT_FILE${NC}"
    # Clear output file
    > "$OUTPUT_FILE"
fi
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

# Function to check if a .mov file is likely an image
# Heuristics:
# 1. Very small files (< 100KB) are likely images
# 2. Files that don't have proper movie headers (we'll use file command)
is_likely_image() {
    local file="$1"
    local size=$(get_file_size "$file")
    
    # Skip if we can't get size
    if [[ "$size" == "unknown" ]]; then
        return 1
    fi
    
    # Very small files are likely images (< 100KB)
    if [[ $size -lt 102400 ]]; then
        return 0
    fi
    
    # Use file command to check MIME type first (more precise)
    local mime_type=$(file --mime-type -b "$file" 2>/dev/null)
    
    # Check MIME type - if it's not a video type, it's suspicious
    if [[ -n "$mime_type" ]] && [[ ! "$mime_type" =~ ^video/ ]]; then
        return 0
    fi
    
    # Use file command to check content type description
    local file_type=$(file -b "$file" 2>/dev/null)
    
    # Look for signs it's not a real movie
    if [[ "$file_type" =~ (JPEG|PNG|GIF|image|bitmap) ]]; then
        return 0
    fi
    
    # If file command says it's data or doesn't recognize it as video, and it's small-ish (< 1MB)
    if [[ $size -lt 1048576 ]] && [[ "$file_type" =~ (data|ASCII|text) ]]; then
        return 0
    fi
    
    # Check for QuickTime files that might be images
    if [[ "$file_type" =~ "QuickTime" ]] && [[ $size -lt 1048576 ]]; then
        # Small QuickTime files might be single-frame "movies" (images)
        return 0
    fi
    
    return 1
}

# Counters
found_files=0
total_mov_files=0

# Find all .mov files
while IFS= read -r -d '' mov_file; do
    ((total_mov_files++))
    
    if is_likely_image "$mov_file"; then
        ((found_files++))
        
        # Get file info
        dir_name=$(dirname "$mov_file")
        file_name=$(basename "$mov_file")
        file_size=$(get_file_size "$mov_file")
        
        # Print file info
        echo -e "${YELLOW}Directory:${NC} $dir_name"
        echo -e "${CYAN}File:${NC} $file_name"
        echo -e "${GREEN}Size:${NC} $(format_file_size "$file_size")"
        
        # Get file type and MIME type for additional info
        mime_type=$(file --mime-type -b "$mov_file" 2>/dev/null || echo "unknown")
        file_type=$(file -b "$mov_file" 2>/dev/null || echo "unknown")
        echo -e "${BLUE}MIME Type:${NC} $mime_type"
        echo -e "${BLUE}File Type:${NC} $file_type"
        echo
        
        # Write photo ID to output file if specified
        if [[ -n "$OUTPUT_FILE" ]]; then
            # Extract photo ID (filename without extension)
            photo_id="${file_name%.mov}"
            echo "$photo_id" >> "$OUTPUT_FILE"
        fi
    fi
done < <(find "$SEARCH_DIR" -type f -name "*.mov" -print0)

echo -e "${GREEN}Summary:${NC}"
echo -e "  Total .mov files found: $total_mov_files"
echo -e "  Likely image files: $found_files"

if [[ $found_files -gt 0 ]]; then
    echo
    echo -e "${YELLOW}The files listed above appear to be images stored as .mov files.${NC}"
    echo -e "${YELLOW}These may have been incorrectly classified by Flickr.${NC}"
    
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo -e "${GREEN}Photo IDs written to: $OUTPUT_FILE${NC}"
        echo -e "${BLUE}You can use this file with flickrbackup.py --download to re-download these files.${NC}"
    fi
else
    echo -e "${GREEN}No suspicious .mov files found - all appear to be legitimate movies.${NC}"
fi
