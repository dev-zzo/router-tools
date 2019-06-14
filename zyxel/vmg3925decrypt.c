/* Decryptor for ZyXEL VMG3925
 * Compile with:
 * gcc -s -Os -o vmg3925decrypt vmg3925decrypt.c -lssl -lcrypto
 * Use:
 * ./vmg3925decrypt [encrypted text with _encrypt_ stripped]
*/

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <openssl/evp.h>
#include <openssl/bio.h>

unsigned char *base64Decode(unsigned char *b64message, size_t* length)
{
	BIO *bio, *b64;
    unsigned char* buffer;
    size_t message_length = strlen((const char *)b64message);

	buffer = (unsigned char*)malloc(message_length);

	bio = BIO_new_mem_buf(b64message, -1);
	b64 = BIO_new(BIO_f_base64());
	bio = BIO_push(b64, bio);

	BIO_set_flags(bio, BIO_FLAGS_BASE64_NO_NL);
	*length = BIO_read(bio, buffer, message_length);
	BIO_free_all(bio);

	return buffer;
}

int aesDecryptCbc256(unsigned char *text, const unsigned char *key)
{
    const unsigned char salt[8] = {0x00, 0x00, 0x30, 0x39, 0x00, 0x00, 0xD4, 0x31};
    unsigned char derived_key[32];
    unsigned char derived_iv[32];
    EVP_CIPHER_CTX ctx;
    size_t text_length;
    unsigned char *decoded_text;
    unsigned char *buffer;
    int out_text_length;
    unsigned char last_block[32];
    int last_block_length;
    
    decoded_text = base64Decode(text, &text_length);
    buffer = malloc(text_length);
    
    if (EVP_BytesToKey(EVP_aes_256_cbc(), EVP_sha1(), salt, key, strlen((const char *)key), 5, derived_key, derived_iv) != 0x20) {
        fprintf(stderr, "cannot derive the keys\n");
        free(decoded_text);
        return -1;
    }
    
    EVP_CIPHER_CTX_init(&ctx);
    if (!EVP_DecryptInit_ex(&ctx, EVP_aes_256_cbc(), NULL, derived_key, derived_iv)) {
        fprintf(stderr, "cannot init decryption\n");
        free(decoded_text);
        return -1;
    }
    EVP_DecryptUpdate(&ctx, buffer, &out_text_length, decoded_text, text_length);
    EVP_DecryptFinal_ex(&ctx, last_block, &last_block_length);
    if (last_block_length) {
        memcpy(&buffer[out_text_length], &last_block[0], last_block_length);
        out_text_length += last_block_length;
    }
    memcpy(text, buffer, out_text_length);
    text[out_text_length] = '\0';
    free(decoded_text);
    return 0;
}

int main(int argc, char *argv[])
{
    const char *key = "ThiSISEncryptioNKeY";
    char *text = argv[1];
    
    OpenSSL_add_all_algorithms();
    aesDecryptCbc256(text, key);
    fprintf(stdout, "Decrypted text: '%s'\n", text);
    
    return 0;
}
