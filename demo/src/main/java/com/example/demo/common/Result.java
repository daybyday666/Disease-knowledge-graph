package com.example.demo.common;

import com.alibaba.fastjson2.JSONObject;
import com.alibaba.fastjson2.JSONWriter;
import lombok.Data;

/**
 * @author ChenJunyu
 * @version 1.0
 * {@code @description:} 统一返回结果类
 * @since 2025-07-09
 */
@Data  // getter和setter 没有的话无法正常生成Result对象，导致浏览器接收返回值异常，报错“no acceptable representation for status code 406”
public class Result<T> {
    /**
     * 状态码
     */
    private Integer code;

    /**
     * 状态信息
     */
    private String message;

    /**
     * 数据
     */
    private T data;


    public Result() {
    }

    public Result(Integer code, String message) {
        this.code = code;
        this.message = message;
    }

    public Result(Integer code, String message, T data) {
        this.code = code;
        this.message = message;
        this.data = data;
    }


    public static <T> Result<T> success(T data) {
        return new Result<>(200, "操作成功", data);
    }

    public static <T> Result<T> success(String message, T data) {
        return new Result<>(200, message, data);
    }

    public static <T> Result<T> success(Integer code, String message) {
        return new Result<>(code, message, null);
    }

    public static <T> Result<T> fail(Integer code, String message) {
        return new Result<>(code, message, null);
    }

    public static <T> Result<T> fail(Integer code, String message, T data) {
        return new Result<>(code, message, data);
    }


    //新增的
    public static <T> Result<T> success(){
        System.out.println("操作成功");
        Result<T> result = new Result<>(200, "操作成功", null);
        System.out.println(result);
        System.out.println(result.asJsonString());
        return result;
    }
    public String asJsonString(){

        return JSONObject.toJSONString(this, JSONWriter.Feature.WriteNulls);
    }
    public static <T> Result<T> unauthorized(String message){
        return fail(401,message);
    }
}
