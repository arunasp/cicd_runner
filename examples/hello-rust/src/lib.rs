pub fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_style_greeting() {
        assert_eq!(greet("World"), "Hello, World!");
    }

    #[test]
    fn named_greeting() {
        assert_eq!(greet("Claude"), "Hello, Claude!");
    }
}
