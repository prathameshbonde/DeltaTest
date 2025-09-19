package com.foo;

public class Bar {
    public String doWork(String input) {
        return input == null ? "" : input.trim().toUpperCase();
    }
}
