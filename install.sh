$RDS_DOMAINS=("https://sciebords-app.uni-muenster.de/" "item 2" "item 3")

for i in $RDS_DOMAINS; do
    connect($i)
done

function connect() {
    $CLIENT_ID=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 64 ; echo '')
    $CLIENT_SECRET=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 64 ; echo '')
    $OAUTHNAME="sciebo-rds"

    # if needed
    # occ market:install oauth2
    occ app:enable oauth2
    occ oauth2:add-client $OAUTHNAME $CLIENT_ID $CLIENT_SECRET $RDS_DOMAIN

    # if needed
    # occ market:install rds
    occ app:enable rds
    occ rds:set-oauthname $OAUTHNAME
    occ rds:set-url $RDS_DOMAIN
}
