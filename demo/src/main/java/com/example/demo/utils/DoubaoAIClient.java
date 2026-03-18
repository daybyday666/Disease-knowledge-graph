package com.example.demo.utils;

import com.alibaba.fastjson2.JSONObject;
import com.example.demo.config.AIConfig;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import kong.unirest.HttpResponse;
import kong.unirest.Unirest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.*;
import java.net.URL;
import java.net.URLConnection;
import java.nio.file.Files;
import java.util.Base64;

/**
 * 豆包AI客户端工具类
 *
 * 该客户端用于与豆包AI模型进行交互，支持文本对话和多模态图像分析功能。
 * 封装豆包AI API的调用逻辑，提供文本请求和图像理解两种核心能力。
 * 支持本地文件和网络URL两种图像输入方式，自动处理图像格式转换和Base64编码。
 * 集成Jackson进行JSON数据处理，使用Unirest进行HTTP请求发送。
 * 配合AIConfig配置类管理API密钥和服务地址，确保安全性和灵活性。
 * 主要用于AI辅助分析、图像识别和智能对话等场景。
 *
 * @author tyuou2
 * @version 1.0
 * @since 2025
 */
@Component
public class DoubaoAIClient {

    private final String apiKey;
    private final String apiUrl;
    private final ObjectMapper mapper = new ObjectMapper();
    /**
     * 构造函数
     *
     * 通过依赖注入获取AI配置信息，初始化API密钥和服务地址。
     * 使用Spring的自动装配机制，确保配置的统一管理。
     *
     * @param aiConfig AI配置对象，包含API密钥和服务地址
     */
    @Autowired
    public DoubaoAIClient(AIConfig aiConfig) {
        this.apiKey = aiConfig.getApiKey();
        this.apiUrl = aiConfig.getApiUrl();
    }

    /**
     * 发送文本请求到豆包AI
     *
     * 向豆包AI发送纯文本对话请求，获取AI的文本回复。
     * 使用doubao-1-5-vision-pro-32k-250115模型进行处理。
     * 构建标准的对话消息格式，设置最大令牌数限制为1000。
     * 适用于文本问答、内容生成和智能对话等场景。
     *
     * @param text 用户输入的文本内容
     * @return AI模型生成的文本回复内容
     * @throws JsonProcessingException 当JSON处理失败时抛出
     */
    public String sendTextRequest(String text) throws JsonProcessingException {
        ObjectNode requestBody = mapper.createObjectNode();
        requestBody.put("model", "doubao-1-5-vision-pro-32k-250115");

        ArrayNode messages = mapper.createArrayNode();
        ObjectNode message = mapper.createObjectNode();
        message.put("role", "user");
        message.put("content", text);
        messages.add(message);

        requestBody.set("messages", messages);
        requestBody.put("max_tokens", 1000);

        String response = Unirest.post(apiUrl)
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .body(requestBody.toString())
                .asString()
                .getBody();
        System.out.println("Doubao API Raw Response: " + response);
        JsonNode root = mapper.readTree(response);
        System.out.println("Doubao API Response: " +root.path("choices")
                .get(0)
                .path("message")
                .path("content")
                .asText());
        return root.path("choices")
                .get(0)
                .path("message")
                .path("content")
                .asText();
    }

    /**
     * 发送图像请求到豆包AI
     *
     * 向豆包AI发送多模态请求，包含图像和文本提示词进行分析。
     * 支持网络URL和本地文件路径两种图像输入方式。
     * 自动检测图像MIME类型，进行Base64编码处理。
     * 构建多模态消息格式，设置最大令牌数为10000支持详细分析。
     *
     * @param imageUrl 图像URL地址或本地文件路径
     * @param prompt 图像分析的文本提示词
     * @return AI模型对图像的分析结果文本
     * @throws IOException 当图像读取或网络请求失败时抛出
     */
    public String sendImageRequest(String imageUrl, String prompt) throws IOException {
        String base64Image;
        String mimeType;
        System.out.println("imageUrl: " + imageUrl);
        System.out.println("prompt: " + prompt);
        // 检查图像URL是否为空
        // 处理URL或本地文件路径
        if (imageUrl.startsWith("http")) {
            // 从URL获取图像
            URL url = new URL(imageUrl);
            URLConnection connection = url.openConnection();
            byte[] imageBytes = connection.getInputStream().readAllBytes();
            base64Image = Base64.getEncoder().encodeToString(imageBytes);
            mimeType = connection.getContentType();
        } else {
            // 从本地文件获取图像
            File imageFile = new File(imageUrl);
            byte[] imageBytes = Files.readAllBytes(imageFile.toPath());
            base64Image = Base64.getEncoder().encodeToString(imageBytes);
            mimeType = Files.probeContentType(imageFile.toPath());
            if (mimeType == null) {
                mimeType = "image/jpeg";
            }
        }

        String dataUri = "data:" + mimeType + ";base64," + base64Image;

        // 构建豆包多模态请求体
        ObjectNode imageContent = mapper.createObjectNode();
        imageContent.put("type", "image_url");
        imageContent.putObject("image_url").put("url", dataUri);

        ObjectNode textContent = mapper.createObjectNode();
        textContent.put("type", "text");
        textContent.put("text", prompt);

        ArrayNode contentArray = mapper.createArrayNode();
        contentArray.add(textContent);
        contentArray.add(imageContent);

        ObjectNode message = mapper.createObjectNode();
        message.put("role", "user");
        message.set("content", contentArray);

        ArrayNode messages = mapper.createArrayNode();
        messages.add(message);

        ObjectNode requestBody = mapper.createObjectNode();
        requestBody.put("model", "doubao-1-5-vision-pro-32k-250115");
        requestBody.set("messages", messages);
        requestBody.put("max_tokens", 10000);

        // 发送API请求
        String response = Unirest.post(apiUrl)
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .body(requestBody.toString())
                .asString()
                .getBody();
        System.out.println("Doubao API Raw Response: " + response);
        JsonNode root = mapper.readTree(response);
        return root.path("choices")
                .get(0)
                .path("message")
                .path("content")
                .asText();
    }

    /**
     * 下载并发送图像请求到豆包AI
     *
     * 从网络URL下载图像，转换为JPG格式后发送给豆包AI进行分析。
     * 创建临时文件存储下载的图像，使用ImageIO进行格式标准化。
     * 自动清理临时文件，确保不占用系统存储空间。
     * 适用于需要格式转换或网络不稳定的图像处理场景。
     * 提供比直接URL方式更可靠的图像处理能力。
     *
     * @param imageUrl 网络图像URL地址
     * @param prompt 图像分析的文本提示词
     * @return AI模型对图像的分析结果文本
     * @throws IOException 当图像下载、格式转换或API请求失败时抛出
     */
    public String downloadAndSendImageRequest(String imageUrl, String prompt) throws IOException {
        // 创建临时文件
        File tempFile = File.createTempFile("ai_image_", ".jpg");

        try {
            // 下载图片
            URL url = new URL(imageUrl);
            try (InputStream in = url.openStream();
                 OutputStream out = new FileOutputStream(tempFile)) {

                // 使用ImageIO进行格式转换
                BufferedImage originalImage = ImageIO.read(in);
                if (originalImage == null) {
                    throw new IOException("无法读取图片或格式不支持");
                }

                // 转换为JPG格式并写入临时文件
                ImageIO.write(originalImage, "jpg", tempFile);

                // 以本地文件方式发送
                return sendImageRequest(tempFile.getAbsolutePath(), prompt);
            }
        } finally {
            // 删除临时文件
            if (tempFile.exists()) {
                tempFile.delete();
            }
        }
    }

    public String callDoubao(String prompt) {
        if (apiUrl == null || !apiUrl.startsWith("http")) {
            throw new IllegalArgumentException("apiUrl 必须为完整的 http(s)://host:port/path 格式，当前为: " + apiUrl);
        }
        JSONObject body = new JSONObject();
        body.put("model", "doubao-1-5-vision-pro-32k-250115");
        com.alibaba.fastjson2.JSONArray messages = new com.alibaba.fastjson2.JSONArray();
        JSONObject message = new JSONObject();
        message.put("role", "user");
        message.put("content", prompt);
        messages.add(message);
        body.put("messages", messages);
        body.put("max_tokens", 1000);

        HttpResponse<kong.unirest.JsonNode> response = Unirest.post(apiUrl)
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .body(body.toJSONString())
                .asJson();

        if (response.getStatus() == 200) {
            String jsonStr = response.getBody().getObject().toString();
            try {
                JsonNode obj = mapper.readTree(jsonStr);
                JsonNode choices = obj.get("choices");
                if (choices != null && choices.isArray() && choices.size() > 0) {
                    return choices.get(0).get("message").get("content").asText();
                } else {
                    throw new RuntimeException("豆包API返回内容为空");
                }
            } catch (Exception e) {
                throw new RuntimeException("解析豆包API响应失败: " + e.getMessage(), e);
            }
        } else {
            throw new RuntimeException("豆包API调用失败: " + response.getStatusText());
        }
    }

}




