package com.example.demo.controller;

import com.example.demo.common.Result;
import com.example.demo.entity.KnowledgeGraphData;
import com.example.demo.service.KnowledgeGraphService;
import com.example.demo.utils.DoubaoAIClient;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.Map;


@RestController
@CrossOrigin
@RequiredArgsConstructor
@RequestMapping("/knowledge-graph")
public class KnowledgeGraphController {
    private final KnowledgeGraphService knowledgeGraphService;
    // src/main/java/com/example/demo/controller/KnowledgeGraphController.java
    @GetMapping("/stats")
    public Result<Map<String, Object>> getGraphStats() {
        try {
            Map<String, Object> stats = knowledgeGraphService.getGraphStats();
            return Result.success("获取图谱统计信息成功", stats);
        } catch (Exception e) {
            return Result.fail(500, "获取图谱统计信息失败: " + e.getMessage());
        }
    }

    @GetMapping("/data")
    public Result<KnowledgeGraphData> getKnowledgeGraph(
            @RequestParam(defaultValue = "50000") int limit) {
        try {
            KnowledgeGraphData data = knowledgeGraphService.getGraphData(limit);
            System.out.println(data);
            return Result.success("获取知识图谱数据成功", data);

        } catch (Exception e) {
            System.out.println("获取知识图谱数据失败: " + e.getMessage());
            return Result.fail(500, "获取知识图谱数据失败: " + e.getMessage());
        }
    }
    // src/main/java/com/example/demo/controller/KnowledgeGraphController.java
    @GetMapping("/subgraph")
    public Result<KnowledgeGraphData> getSubGraphByDisease(
            @RequestParam String disease,
            @RequestParam(defaultValue = "100") int limit) {
        try {
            KnowledgeGraphData data = knowledgeGraphService.getSubGraphByDisease(disease, limit);
            return Result.success("获取子图谱成功", data);
        } catch (Exception e) {
            return Result.fail(500, "获取子图谱失败: " + e.getMessage());
        }
    }

    @PostMapping("/ask")
    public Result<String> askKnowledgeGraph(@RequestBody Map<String, String> body) {
        String question = body.get("question");
        String doubaoResult = knowledgeGraphService.askByDoubao(question);
        return Result.success("查询成功", doubaoResult);
    }

    @GetMapping("/subgraph-by-symptom")
    public Result<KnowledgeGraphData> getSubGraphBySymptom(
            @RequestParam String symptom,
            @RequestParam(defaultValue = "100") int limit) {
        try {
            KnowledgeGraphData data = knowledgeGraphService.getSubGraphBySymptom(symptom, limit);
            return Result.success("获取子图谱成功", data);
        } catch (Exception e) {
            return Result.fail(500, "获取子图谱失败: " + e.getMessage());
        }
    }
}
