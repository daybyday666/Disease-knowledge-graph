package com.example.demo.service;

import com.example.demo.entity.KnowledgeGraphData;

import java.util.Map;

public interface KnowledgeGraphService {
    public KnowledgeGraphData getGraphData(int limit) ;
    // src/main/java/com/example/demo/service/KnowledgeGraphService.java
    KnowledgeGraphData getSubGraphByDisease(String disease, int limit);
    String askByDoubao(String question);
    // 在 KnowledgeGraphService 接口中添加方法声明
    KnowledgeGraphData getSubGraphBySymptom(String symptom, int limit);
    // src/main/java/com/example/demo/service/KnowledgeGraphService.java
    Map<String, Object> getGraphStats();

}
