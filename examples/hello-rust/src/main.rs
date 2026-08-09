use std::env;
use hello_rust_example::greet;

fn main() {
    let name = env::args().nth(1).unwrap_or_else(|| "World".to_string());
    println!("{}", greet(&name));
}
