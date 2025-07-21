#!/bin/bash

# Script to find .mov files that likely contain images instead of actual movies
# Usage: ./find_image_movies.sh [--verbose] [directory] [output_file]
# If no directory specified, uses current directory
# If output_file specified, writes photo IDs (filename without extension) to file
# --verbose: Show all .mov files as they are processed

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse command line arguments
VERBOSE=false
SEARCH_DIR=""
OUTPUT_FILE=""

for arg in "$@"; do
    case $arg in
        --verbose)
            VERBOSE=true
            shift
            ;;
        *)
            if [[ -z "$SEARCH_DIR" ]]; then
                SEARCH_DIR="$arg"
            elif [[ -z "$OUTPUT_FILE" ]]; then
                OUTPUT_FILE="$arg"
            fi
            shift
            ;;
    esac
done

# Set default directory if not specified
SEARCH_DIR="${SEARCH_DIR:-.}"

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
        echo "unknown"
    elif [[ $size -lt 1024 ]]; then
        echo "${size}B"
    elif [[ $size -lt 1048576 ]]; then
        echo "$(( size / 1024 ))KB"
    else
        echo "$(( size / 1048576 ))MB"
    fi
}

# Function to format MIME type for display (short version)
format_mime_type() {
    local mime_type="$1"
    echo "$mime_type"
}

# Function to check if a .mov file is likely a real movie
# Uses MIME type detection - if it's video/*, it's likely a real movie
is_likely_movie() {
    local file="$1"
   
    # Use file command to check MIME type
    local mime_type=$(file --mime-type -b "$file" 2>/dev/null)
    
    # Check MIME type - if it's a video type, it's likely a real movie
    if [[ -n "$mime_type" ]] && [[ "$mime_type" =~ ^video/ ]]; then
        return 0  # It's a video MIME type, so likely a real movie
    fi
    
    return 1  # Not a video MIME type, so likely not a real movie
}

# Counters
found_files=0
total_mov_files=0

echo -e "${BLUE}Scanning for .mov files...${NC}"
if [[ "$VERBOSE" == true ]]; then
    echo -e "${BLUE}Showing all .mov files found:${NC}"
else
    echo -e "${BLUE}Showing only suspected non-video files:${NC}"
fi
echo

# Find all .mov files
while IFS= read -r -d '' mov_file; do
    total_mov_files=$((total_mov_files + 1))
    
    file_name=$(basename "$mov_file")
    file_size=$(get_file_size "$mov_file")
    mime_type=$(file --mime-type -b "$mov_file" 2>/dev/null || echo "unknown")
    formatted_size=$(format_file_size "$file_size")
    
    if is_likely_movie "$mov_file"; then
        # It's a real movie
        if [[ "$VERBOSE" == true ]]; then
            echo -e "${GREEN}${mov_file}${NC} | ${mime_type} | ${formatted_size}"
        fi
    else
        # Suspected non-video file
        found_files=$((found_files + 1))
        echo -e "${YELLOW}${mov_file}${NC} | ${mime_type} | ${formatted_size}"
        
        # Write photo ID to output file if specified
        if [[ -n "$OUTPUT_FILE" ]]; then
            # Extract photo ID (filename without extension)
            photo_id="${file_name%.mov}"
            echo "$photo_id" >> "$OUTPUT_FILE"
        fi
    fi
done < <(find "$SEARCH_DIR" -type f -name "*.mov" -print0)

echo
echo -e "${GREEN}Summary:${NC}"
echo -e "  Total .mov files found: $total_mov_files"
echo -e "  Suspected non-video files: $found_files"

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
