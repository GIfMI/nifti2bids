#!/usr/bin/env bash

set -euo pipefail

OUT="sequence_classification.csv"

echo "count,SequenceName,ProtocolName,Manufacturer,ImageType,BIDS_datatype,BIDS_suffix,BIDS_entities,Comments" > "$OUT"

find -L NIFTIGZ_ONLY -name "*.json" -exec jq -r '
[
  (.SequenceName // "NA"),
  (.ProtocolName // "NA"),
  (.Manufacturer // "NA"),
  (
    if (.ImageType | type) == "array"
    then (.ImageType | join("+"))
    else (.ImageType | tostring)
    end
  )
] | @tsv
' {} \; |
sort |
uniq -c |
sort -nr |
while read -r COUNT REST
do

    # Parse TSV fields safely (protocol names may contain spaces)
    IFS=$'\t' read -r SEQ PROT MANUF IMGTYPE <<< "$REST"

    DATATYPE=""
    SUFFIX=""
    ENTITIES=""
    COMMENT=""

    # -------------------------
    # Ignore scouts/localizers
    # -------------------------

    if [[ "$PROT" =~ scout|localizer ]]; then
        COMMENT="IGNORE"
    fi

    # -------------------------
    # T1w
    # -------------------------

    if [[ "$PROT" =~ mprage ]]; then
        DATATYPE="anat"
        SUFFIX="T1w"

        if [[ "$PROT" =~ gd ]]; then
            ENTITIES="ce-gadolinium"
        fi
    fi

    if [[ "$PROT" =~ T1W_3D ]]; then
        DATATYPE="anat"
        SUFFIX="T1w"

        if [[ "$PROT" =~ GD|gd ]]; then
            ENTITIES="ce-gadolinium"
        fi
    fi

    # -------------------------
    # FLAIR
    # -------------------------

    if [[ "$PROT" =~ flair|FLAIR|dark-fluid|spcir ]]; then
        DATATYPE="anat"
        SUFFIX="FLAIR"

        if [[ "$PROT" =~ gd ]]; then
            ENTITIES="ce-gadolinium"
        fi
    fi

    # -------------------------
    # T2w
    # -------------------------

    if [[ "$PROT" =~ ^T2\ AXIAAL$ ]]; then
        DATATYPE="anat"
        SUFFIX="T2w"
    fi

    # -------------------------
    # SWI
    # -------------------------

    if [[ "$PROT" =~ swi ]]; then
        DATATYPE="anat"
        SUFFIX="swi"

        if [[ "$IMGTYPE" =~ PHASE ]]; then
            ENTITIES="part-phase"
        elif [[ "$IMGTYPE" =~ MAGNITUDE ]]; then
            ENTITIES="part-mag"
        fi

        if [[ "$IMGTYPE" =~ SWI ]]; then
            COMMENT="derived SWI image"
        fi
    fi

    # -------------------------
    # Diffusion
    # -------------------------

    if [[ "$PROT" =~ dwi|diff ]]; then
        DATATYPE="dwi"
        SUFFIX="dwi"
    fi

    if [[ "$PROT" =~ PA_30dir_b0 ]]; then
        DATATYPE="fmap"
        SUFFIX="epi"
        ENTITIES="dir-PA"
    fi

    if [[ "$PROT" =~ AP_30dir_b1000 ]]; then
        DATATYPE="dwi"
        SUFFIX="dwi"
        ENTITIES="dir-AP"
    fi

    # -------------------------
    # TOF
    # -------------------------

    if [[ "$PROT" =~ tof ]]; then
        DATATYPE="anat"
        SUFFIX="angio"
    fi

    # -------------------------
    # Magnetization Transfer
    # -------------------------

    if [[ "$PROT" =~ "MT ON" ]]; then
        DATATYPE="anat"
        SUFFIX="MT"
        ENTITIES="mt-on"
    fi

    if [[ "$PROT" =~ "MT OFF" ]]; then
        DATATYPE="anat"
        SUFFIX="MT"
        ENTITIES="mt-off"
    fi

    # -------------------------
    # Derived products
    # -------------------------

    if [[ "$IMGTYPE" =~ ADC ]]; then
        COMMENT="derived ADC - exclude"
    fi

    if [[ "$IMGTYPE" =~ TRACEW ]]; then
        COMMENT="derived TRACE - exclude"
    fi

    if [[ "$IMGTYPE" =~ FA ]]; then
        COMMENT="derived FA - exclude"
    fi

    if [[ "$IMGTYPE" =~ MIP ]]; then
        COMMENT="derived MIP - exclude"
    fi

    if [[ "$IMGTYPE" =~ MPR ]]; then
        COMMENT="derived MPR - exclude"
    fi

    printf '%s,"%s","%s","%s","%s","%s","%s","%s","%s"\n' \
        "$COUNT" \
        "$SEQ" \
        "$PROT" \
        "$MANUF" \
        "$IMGTYPE" \
        "$DATATYPE" \
        "$SUFFIX" \
        "$ENTITIES" \
        "$COMMENT"

done >> "$OUT"

echo "Wrote $OUT"