package tokens

import "unicode/utf8"

func ClampChars(s string, max int) string {
	if max <= 0 {
		return s
	}
	if len(s) <= max {
		return s
	}
	// Keep UTF-8 integrity
	if utf8.ValidString(s[:max]) {
		return s[:max]
	}
	for max > 0 {
		max--
		if utf8.ValidString(s[:max]) {
			return s[:max]
		}
	}
	return ""
}
