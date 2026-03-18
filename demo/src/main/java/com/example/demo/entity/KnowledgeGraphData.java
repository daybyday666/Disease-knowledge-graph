package com.example.demo.entity;

import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class KnowledgeGraphData {
    private List<Node> nodes;
    private List<Edge> edges;

    @Data
    public static class Node {
        private String id;
        private String label;
        private Map<String, Object> properties; // 新增
    }

    @Data
    public static class Edge {
        private String source;
        private String target;
        private String label;
        private Map<String, Object> properties; // 新增
    }
}
