package com.foo;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public class BazTest {
    @Test
    public void testDoIt() {
        Baz b = new Baz();
        assertEquals("HELLO!", b.doIt(" hello"));
    }
}
