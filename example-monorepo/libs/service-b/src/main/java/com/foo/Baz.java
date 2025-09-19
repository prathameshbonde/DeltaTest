package com.foo;

public class Baz {
    public String doIt(String s) {
        Bar dep = new Bar();
        return dep.doWork(s) + "!";
    }
}
