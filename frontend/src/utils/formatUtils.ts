/**
 * Formats a number with commas as thousands separators
 * @param num - The number to format
 * @returns Formatted number string
 */
export function formatNumber(num: number): string {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Truncates a string to a specified length and adds an ellipsis if necessary
 * @param text - The string to truncate
 * @param maxLength - The maximum length of the string
 * @returns Truncated string
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.slice(0, maxLength - 3) + "...";
}