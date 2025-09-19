package com.example.tools;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;

/**
 * Heuristic mapper from JUnit test methods to covered classes/methods.
 * Strategy:
 * - Find test classes under src/test/java
 * - For each test method annotated with @Test, scan for any Foo.bar(...) calls
 *   and map to FQCN if it matches project package roots using a simple resolver.
 * Note: This is a naive static approach for demo purposes.
 */
public class TestMapper {
    public static void main(String[] args) throws Exception {
        Path root = Paths.get(args.length > 0 ? args[0] : ".").toAbsolutePath().normalize();
        List<Map<String, Object>> mapping = new ArrayList<>();

        List<Path> testFiles = new ArrayList<>();
        try {
            Files.walk(root)
                .filter(p -> p.toString().replace('\\','/').contains("/src/test/java/") && p.toString().endsWith(".java"))
                .forEach(testFiles::add);
        } catch (IOException e) {
            // ignore
        }

        Pattern pkgPattern = Pattern.compile("^package\\s+([a-zA-Z0-9_.]+);", Pattern.MULTILINE);
        Pattern clsPattern = Pattern.compile("class\\s+([A-Za-z0-9_]+)");
        Pattern testMethodPattern = Pattern.compile("@Test[\\s\\S]*?\\n\\s*public\\s+void\\s+([A-Za-z0-9_]+)\\s*\\(");
        Pattern callPattern = Pattern.compile("([A-Za-z0-9_$.]+)#?([a-zA-Z0-9_]+)\\s*\\("); // for explanations
        Pattern dotCallPattern = Pattern.compile("([A-Za-z0-9_$.]+)\\.([a-zA-Z0-9_]+)\\s*\\(");

        for (Path tf : testFiles) {
            String src = Files.readString(tf);
            String pkg = findFirst(pkgPattern, src, 1).orElse("");
            String cls = findFirst(clsPattern, src, 1).orElse(tf.getFileName().toString().replace(".java",""));
            String fqTestClass = pkg.isEmpty()? cls : pkg + "." + cls;

            Matcher tm = testMethodPattern.matcher(src);
            while (tm.find()) {
                String testMethod = tm.group(1);
                Set<String> covers = new LinkedHashSet<>();
                Matcher dm = dotCallPattern.matcher(src.substring(tm.start(), Math.min(src.length(), tm.end()+2000)));
                while (dm.find()) {
                    String targetClass = dm.group(1);
                    String targetMethod = dm.group(2);
                    if (Character.isUpperCase(targetClass.charAt(0))) {
                        // naive assumption of Class.method
                        covers.add(targetClass + "#" + targetMethod);
                    }
                }
                Map<String,Object> entry = new LinkedHashMap<>();
                entry.put("test", fqTestClass + "#" + testMethod);
                entry.put("covers", new ArrayList<>(covers));
                mapping.add(entry);
            }
        }

        Path out = root.resolve("tools/output/test_mapping.json");
        Files.createDirectories(out.getParent());
        try (Writer w = Files.newBufferedWriter(out)) {
            w.write(toJson(mapping));
        }
        System.out.println("Wrote " + out);
    }

    private static Optional<String> findFirst(Pattern p, String s, int group) {
        Matcher m = p.matcher(s);
        if (m.find()) return Optional.ofNullable(m.group(group));
        return Optional.empty();
    }

    private static String toJson(List<Map<String,Object>> list) {
        StringBuilder sb = new StringBuilder();
        sb.append("[\n");
        for (int i=0;i<list.size();i++) {
            Map<String,Object> m = list.get(i);
            sb.append("  {");
            sb.append("\"test\": \"").append(escape((String)m.get("test"))).append("\",");
            @SuppressWarnings("unchecked") List<String> covers = (List<String>) m.get("covers");
            sb.append(" \"covers\": [");
            for (int j=0;j<covers.size();j++) {
                sb.append("\"").append(escape(covers.get(j))).append("\"");
                if (j+1 < covers.size()) sb.append(", ");
            }
            sb.append("]");
            sb.append(" }");
            if (i+1<list.size()) sb.append(",");
            sb.append("\n");
        }
        sb.append("]\n");
        return sb.toString();
    }

    private static String escape(String s) {
        return s.replace("\\","\\\\").replace("\"","\\\"");
    }
}
