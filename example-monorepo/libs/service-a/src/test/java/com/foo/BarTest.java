package com.foo;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

public class BarTest {
    @Test
    public void testDoWork() {
        Bar b = new Bar();
        assertEquals("HELLO", b.doWork("  hello "));
    }
}
