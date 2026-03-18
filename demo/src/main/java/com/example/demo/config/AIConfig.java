package com.example.demo.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

/**
 * AI服务配置类
 *
 * 该配置类负责管理AI服务的相关配置参数，包括服务提供商、API密钥和API地址等。
 * 通过读取配置文件中的属性值，为AI服务组件提供必要的配置信息。
 */
@Configuration //标记这是一个Spring配置类，Spring容器会自动扫描并注册为Bean
public class AIConfig {
    /** AI服务提供商名称 */
    @Value("${ai.provider}")//从配置文件中读取ai.provider属性值并注入到provider字段
    private String provider;
    /** 豆包AI服务的API密钥 */
    @Value("${ai.doubao.api-key}")
    private String apiKey;
    /** 豆包AI服务的API地址 */
    @Value("${ai.doubao.api-url}")
    private String apiUrl;

    /**
     * 获取AI服务提供商名称
     *
     * @return String AI服务提供商名称
     */
    public String getProvider() {
        return provider;
    }

    /**
     * 获取豆包AI服务的API密钥
     *
     * @return String API密钥
     */
    public String getApiKey() {
        return apiKey;
    }

    /**
     * 获取豆包AI服务的API地址
     *
     * @return String API服务地址
     */
    public String getApiUrl() {
        return apiUrl;
    }
}