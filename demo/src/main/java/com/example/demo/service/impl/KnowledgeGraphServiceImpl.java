package com.example.demo.service.impl;

import com.example.demo.entity.KnowledgeGraphData;
import com.example.demo.service.KnowledgeGraphService;

import kong.unirest.json.JSONObject;
import lombok.RequiredArgsConstructor;
import org.neo4j.driver.*;
import org.neo4j.driver.types.Relationship;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import com.example.demo.utils.DoubaoAIClient;
import java.lang.Record;
import java.util.*;


@Service
@RequiredArgsConstructor
public class KnowledgeGraphServiceImpl implements KnowledgeGraphService {

    private final Driver driver;
    private final DoubaoAIClient DoubaoAIClient;
    @Value("${spring.neo4j.database}")
    private String database;


    @Value("${ai.doubao.api-key}")
    private String apiKey;
    @Value("${ai.doubao.api-key}")
    private String apiUrl;

    @Override
    public KnowledgeGraphData getGraphData(int limit) {
        try (Session session = driver.session(SessionConfig.forDatabase(database))) {
            // 查询所有节点
            String nodesQuery = "MATCH (n) RETURN n LIMIT $limit";
            Result nodesResult = session.run(nodesQuery, org.neo4j.driver.Values.parameters("limit", limit));
            List<KnowledgeGraphData.Node> nodes = new ArrayList<>();
            nodesResult.forEachRemaining(record -> {
                org.neo4j.driver.types.Node neoNode = record.get("n").asNode();
                System.out.println("查到节点: " + neoNode.asMap()); // 打印所有属性
                KnowledgeGraphData.Node node = new KnowledgeGraphData.Node();
                node.setId(String.valueOf(neoNode.id()));
                node.setLabel(neoNode.labels().iterator().hasNext() ? neoNode.labels().iterator().next() : "");
                node.setProperties(neoNode.asMap());
                nodes.add(node);
            });


            // 查询所有关系
            String edgesQuery = "MATCH (s)-[r]->(t) RETURN id(s) as source, id(t) as target, type(r) as label, properties(r) as props LIMIT $limit";
            Result edgesResult = session.run(edgesQuery, org.neo4j.driver.Values.parameters("limit", limit));
            List<KnowledgeGraphData.Edge> edges = new ArrayList<>();
            edgesResult.forEachRemaining(record -> {
                KnowledgeGraphData.Edge edge = new KnowledgeGraphData.Edge();
                edge.setSource(String.valueOf(record.get("source").asLong()));
                edge.setTarget(String.valueOf(record.get("target").asLong()));
                edge.setLabel(record.get("label").asString());
                edge.setProperties(record.get("props").asMap());
                edges.add(edge);
            });

            KnowledgeGraphData graphData = new KnowledgeGraphData();
            graphData.setNodes(nodes);
            graphData.setEdges(edges);

            return graphData;
        }
    }

    @Override
    public KnowledgeGraphData getSubGraphByDisease(String disease, int limit) {
        try (Session session = driver.session(SessionConfig.forDatabase(database))) {
            // 1. 节点查询：使用实际中文标签“疾病”，而非“Disease”
            String nodesQuery = "MATCH (d:疾病 {name: $disease})-[*0..1]-(n) RETURN DISTINCT n LIMIT $limit";
            Result nodesResult = session.run(nodesQuery, org.neo4j.driver.Values.parameters("disease", disease, "limit", limit));

            List<KnowledgeGraphData.Node> nodes = new ArrayList<>();
            Set<Long> nodeIdSet = new HashSet<>();

            // 打印查询参数和结果数量，方便调试
            System.out.println("查询的疾病名称：" + disease);
            nodesResult.forEachRemaining(record -> {
                org.neo4j.driver.types.Node neoNode = record.get("n").asNode();
                nodeIdSet.add(neoNode.id());
                // 打印节点详情：标签+属性，确认是否正确
                System.out.println("匹配到节点：标签=" + neoNode.labels() + "，属性=" + neoNode.asMap());

                KnowledgeGraphData.Node node = new KnowledgeGraphData.Node();
                node.setId(String.valueOf(neoNode.id()));
                node.setLabel(String.join(",", neoNode.labels())); // 存储实际标签（如“疾病”“症状”等）
                node.setProperties(neoNode.asMap()); // 存储节点具体属性（如名称、描述等）
                nodes.add(node);
            });

            System.out.println("查询到的相关节点总数：" + nodeIdSet.size()); // 确认是否有节点

            // 2. 关系查询：基于查询到的节点ID查询关系
            String edgesQuery = "MATCH (a)-[r]-(b) WHERE id(a) IN $ids AND id(b) IN $ids RETURN id(a) as source, id(b) as target, type(r) as label, properties(r) as props LIMIT $limit";
            Result edgesResult = session.run(edgesQuery, org.neo4j.driver.Values.parameters("ids", nodeIdSet, "limit", limit));

            List<KnowledgeGraphData.Edge> edges = new ArrayList<>();
            edgesResult.forEachRemaining(record -> {
                KnowledgeGraphData.Edge edge = new KnowledgeGraphData.Edge();
                edge.setSource(String.valueOf(record.get("source").asLong()));
                edge.setTarget(String.valueOf(record.get("target").asLong()));
                edge.setLabel(record.get("label").asString());
                edge.setProperties(record.get("props").asMap());
                edges.add(edge);
            });

            System.out.println("查询到的关系总数：" + edges.size()); // 确认是否有关系

            KnowledgeGraphData graphData = new KnowledgeGraphData();
            graphData.setNodes(nodes);
            graphData.setEdges(edges);
            return graphData;
        }
    }

    @Override
    public String askByDoubao(String question) {
        String prompt = "请分析用户问题，提取核心实体和关系，并生成Neo4j Cypher语句，已知领域知识：\n" +
                "- 节点标签包括：疾病、症状、病因、治疗、诊断方法、科室（标签为中文）\n" +
                "- 关系类型包括：疾病-[有症状]->症状，疾病-[由引起]->病因，疾病-[可治疗]->治疗等返回JSON，示例：{\"entities\": [\"感冒\", \"症状\"], \"cypher\": \"MATCH (d:疾病 {name: '感冒'})-[:有症状]->(s:症状) RETURN d, s\"}。用户问题：" + question;
        String doubaoresponse1 = DoubaoAIClient.callDoubao(prompt);

        JSONObject json = new JSONObject(doubaoresponse1);
        String cypher = json.getString("cypher");
        if (cypher == null || cypher.isEmpty()) {
            return "未能从豆包API获取到Cypher语句";
        }
        // 3. 执行Cypher查询
        List<JSONObject> queryResult = new ArrayList<>();
        try (Session session = driver.session(SessionConfig.forDatabase(database))) {
            Result result = session.run(cypher);
            while (result.hasNext()) {
                org.neo4j.driver.Record record = result.next();
                JSONObject row = new JSONObject();
                for (String key : record.keys()) {
                    row.put(key, record.get(key).toString());
                }
                queryResult.add(row);
            }
        } catch (Exception e) {
            return "执行Cypher查询出错: " + e.getMessage();
        }

        // 4. 组装新prompt，再次调用豆包API生成建议
        String prompt2 = "用户问题：" + question + "，查询结果：" + queryResult.toString() + "，请基于这些信息用简洁自然语言生成建议或答案。";
        String doubaoResult2 = DoubaoAIClient.callDoubao(prompt2);

        // 5. 返回最终建议
        return doubaoResult2;
    }
    // src/main/java/com/example/demo/service/impl/KnowledgeGraphServiceImpl.java
    @Override
    public Map<String, Object> getGraphStats() {
        Map<String, Object> stats = new HashMap<>();
        try (Session session = driver.session(SessionConfig.forDatabase(database))) {
            // 统计疾病节点数量
            long diseaseCount = session.run("MATCH (n:疾病) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("diseaseCount", diseaseCount);

            // 统计症状节点数量
            long symptomCount = session.run("MATCH (n:症状) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("symptomCount", symptomCount);

            // 统计药物节点数量
            long drugCount = session.run("MATCH (n:诊断方法) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("drugCount", drugCount);


            long keshi = session.run("MATCH (n:科室) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("keshi", keshi);

            long treatment = session.run("MATCH (n:治疗) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("treatment", treatment);
            long reason = session.run("MATCH (n:病因) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("reason", reason);
            // 统计所有节点数量
            long nodeCount = session.run("MATCH (n) RETURN count(n) AS count")
                    .single().get("count").asLong();
            stats.put("nodeCount", nodeCount);

            // 统计所有关系数量
            long relCount = session.run("MATCH ()-[r]->() RETURN count(r) AS count")
                    .single().get("count").asLong();
            stats.put("relationCount", relCount);
        }
        return stats;
    }
    @Override
    public KnowledgeGraphData getSubGraphBySymptom(String symptom, int limit) {
        try (Session session = driver.session(SessionConfig.forDatabase(database))) {
            // 1. 查询症状相关节点
            String nodesQuery = "MATCH (s:症状 {name: $symptom})-[*0..1]-(n) RETURN DISTINCT n LIMIT $limit";
            Result nodesResult = session.run(nodesQuery, org.neo4j.driver.Values.parameters("symptom", symptom, "limit", limit));

            List<KnowledgeGraphData.Node> nodes = new ArrayList<>();
            Set<Long> nodeIdSet = new HashSet<>();
            nodesResult.forEachRemaining(record -> {
                org.neo4j.driver.types.Node neoNode = record.get("n").asNode();
                nodeIdSet.add(neoNode.id());
                KnowledgeGraphData.Node node = new KnowledgeGraphData.Node();
                node.setId(String.valueOf(neoNode.id()));
                node.setLabel(String.join(",", neoNode.labels()));
                node.setProperties(neoNode.asMap());
                nodes.add(node);
            });

            // 2. 查询相关关系
            String edgesQuery = "MATCH (a)-[r]-(b) WHERE id(a) IN $ids AND id(b) IN $ids RETURN id(a) as source, id(b) as target, type(r) as label, properties(r) as props LIMIT $limit";
            Result edgesResult = session.run(edgesQuery, org.neo4j.driver.Values.parameters("ids", nodeIdSet, "limit", limit));

            List<KnowledgeGraphData.Edge> edges = new ArrayList<>();
            edgesResult.forEachRemaining(record -> {
                KnowledgeGraphData.Edge edge = new KnowledgeGraphData.Edge();
                edge.setSource(String.valueOf(record.get("source").asLong()));
                edge.setTarget(String.valueOf(record.get("target").asLong()));
                edge.setLabel(record.get("label").asString());
                edge.setProperties(record.get("props").asMap());
                edges.add(edge);
            });

            KnowledgeGraphData graphData = new KnowledgeGraphData();
            graphData.setNodes(nodes);
            graphData.setEdges(edges);
            return graphData;
        }

    }

}